import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_company_member
from app.db.session import get_db
from app.events.publisher import publish_event
from app.models import (
    Batch,
    Document,
    DocumentStatus,
    OcrResult,
    Page,
    Template,
    User,
    UserRole,
)
from app.schemas.document import (
    BatchOut,
    DocumentListOut,
    DocumentOut,
    OcrResultOut,
    PageOut,
)
from app.services import documents as doc_service
from app.services import storage
from app.services.audit import log_action

router = APIRouter(tags=["documents"])


def _is_admin(user: User) -> bool:
    return user.role in (UserRole.company_admin.value, UserRole.super_admin.value)


def _can_see(user: User, document: Document) -> bool:
    """A member sees shared docs and their own; admins see everything."""
    if _is_admin(user):
        return True
    return document.visibility == "shared" or document.uploaded_by_user_id == user.id


def _visible_documents(user: User):
    """Base query scoped to what this user may see."""
    query = select(Document).where(Document.company_id == user.company_id)
    if not _is_admin(user):
        query = query.where(
            or_(Document.visibility == "shared", Document.uploaded_by_user_id == user.id)
        )
    return query


def _get_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.company_id != user.company_id or not _can_see(user, document):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


def _get_page(db: Session, user: User, page_id: uuid.UUID) -> Page:
    page = db.get(Page, page_id)
    if page is None or page.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    return page


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    doc_type: str = "other",
    template_id: uuid.UUID | None = None,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    if template_id is not None:
        template = db.get(Template, template_id)
        if template is None or template.company_id != user.company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    content = await file.read()
    try:
        document = doc_service.create_document(
            db,
            company_id=user.company_id,
            filename=file.filename or "upload.bin",
            content=content,
            uploaded_by_user_id=user.id,
            doc_type=doc_type,
        )
        document.template_id = template_id
        # A person's own upload is private by default (owner + admins see it);
        # they can share it later. Scanner/device uploads stay shared.
        document.visibility = "private"
    except doc_service.DuplicateDocumentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "Duplicate document", "existing_id": str(exc.existing_id)},
        )
    except doc_service.UnsupportedFileTypeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
    log_action(db, "document.upload", company_id=user.company_id, actor_user_id=user.id,
               target_type="document", target_id=str(document.id))
    db.commit()
    publish_event(user.company_id, "documents.changed", {"action": "uploaded"})
    # Interactive uploads get priority over bulk scanner batches.
    doc_service.enqueue_ocr(document, priority=5)
    return document


@router.get("/documents", response_model=DocumentListOut)
def list_documents(
    status_filter: str | None = None,
    doc_type: str | None = None,
    batch_id: uuid.UUID | None = None,
    q: str | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    mine: bool = False,
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = _visible_documents(user)
    if mine:
        query = query.where(Document.uploaded_by_user_id == user.id)
    if status_filter:
        query = query.where(Document.status == status_filter)
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if batch_id:
        query = query.where(Document.batch_id == batch_id)
    if q:
        query = query.where(Document.original_filename.ilike(f"%{q}%"))
    if created_from:
        start = datetime.combine(created_from, time.min, tzinfo=timezone.utc)
        query = query.where(Document.created_at >= start)
    if created_to:
        # Inclusive of the whole end day.
        end = datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        query = query.where(Document.created_at < end)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DocumentListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/documents/reclassify")
def reclassify_documents(
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """Backfill category (区分) AND extracted fields for already-processed
    documents from their stored OCR result — for documents scanned before
    auto-classification/extraction existed. No re-OCR."""
    from app.services.classify import detect_category
    from app.services.extraction import extract_document

    query = _visible_documents(user).where(
        Document.status.in_(
            [DocumentStatus.completed.value, DocumentStatus.partially_failed.value]
        )
    )
    documents = db.scalars(query).all()
    updated = 0
    for document in documents:
        changed = False
        # Category — only when not already detected.
        if document.doc_type in (None, "", "other"):
            path = storage.document_markdown_path(document.company_id, document.id)
            if path.exists():
                try:
                    detected = detect_category(path.read_text(encoding="utf-8"))
                except OSError:
                    detected = None
                if detected:
                    document.doc_type = detected
                    changed = True
        # Fields — extract when missing (built-in common fields for no-template).
        if not document.extracted_json:
            try:
                if extract_document(db, document):
                    changed = True
            except Exception:
                pass
        if changed:
            updated += 1
    db.commit()
    if updated:
        publish_event(user.company_id, "documents.changed", {"action": "reclassified"})
    return {"updated": updated, "scanned": len(documents)}


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    return _get_document(db, user, document_id)


@router.get("/documents/{document_id}/markdown", response_class=PlainTextResponse)
def get_document_markdown(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    document = _get_document(db, user, document_id)
    path = storage.document_markdown_path(document.company_id, document.id)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Markdown not available yet")
    return path.read_text(encoding="utf-8")


@router.get("/documents/{document_id}/download")
def download_document_markdown(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    document = _get_document(db, user, document_id)
    path = storage.document_markdown_path(document.company_id, document.id)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Markdown not available yet")
    filename = f"{document.original_filename.rsplit('.', 1)[0]}.md"
    return FileResponse(path, media_type="text/markdown", filename=filename)


@router.get("/documents/export/bulk-xlsx")
def export_documents_bulk(
    status_filter: str | None = None,
    doc_type: str | None = None,
    q: str | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """One Excel of every (filtered) completed document's extracted fields."""
    from urllib.parse import quote

    from fastapi.responses import Response

    from app.services.classify import CATEGORY_LABELS_JA
    from app.services.export import documents_bulk_xlsx
    from app.services.extraction import extract_document

    query = _visible_documents(user).where(
        Document.status.in_(
            [DocumentStatus.completed.value, DocumentStatus.partially_failed.value]
        )
    )
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if q:
        query = query.where(Document.original_filename.ilike(f"%{q}%"))
    if created_from:
        start = datetime.combine(created_from, time.min, tzinfo=timezone.utc)
        query = query.where(Document.created_at >= start)
    if created_to:
        end = datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        query = query.where(Document.created_at < end)
    documents = db.scalars(query.order_by(Document.created_at.desc())).all()

    # Backfill fields on the fly for documents processed before auto-extraction
    # existed, so the export always carries the data — no manual reclassify.
    dirty = False
    for document in documents:
        if not document.extracted_json:
            try:
                if extract_document(db, document):
                    dirty = True
            except Exception:
                pass
    if dirty:
        db.commit()

    label = CATEGORY_LABELS_JA.get(doc_type or "", "") if doc_type else ""
    title = f"{label}抽出一覧" if label else "文書抽出一覧"
    data = documents_bulk_xlsx(documents, title=title)
    filename = quote(f"{title}.xlsx")
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/documents/{document_id}/export/pdf")
def export_document_pdf(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from fastapi.responses import Response

    from app.services.export import document_to_pdf

    document = _get_document(db, user, document_id)
    data = document_to_pdf(db, document)
    stem = document.original_filename.rsplit(".", 1)[0]
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(stem)}.pdf"},
    )


@router.get("/documents/{document_id}/export/xlsx")
def export_document_xlsx(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote

    from fastapi.responses import Response

    from app.services.export import document_to_xlsx

    document = _get_document(db, user, document_id)
    data = document_to_xlsx(db, document)
    stem = document.original_filename.rsplit(".", 1)[0]
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(stem)}.xlsx"},
    )


@router.patch("/documents/{document_id}/visibility", response_model=DocumentOut)
def set_visibility(
    document_id: uuid.UUID,
    visibility: str,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """Owner (or admin) toggles a document between private and shared."""
    if visibility not in ("private", "shared"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "visibility must be private or shared")
    document = _get_document(db, user, document_id)
    if not _is_admin(user) and document.uploaded_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can change visibility")
    document.visibility = visibility
    db.commit()
    publish_event(user.company_id, "documents.changed", {"action": "visibility"})
    return document


class ClaimBulkIn(BaseModel):
    document_ids: list[uuid.UUID]


@router.post("/documents/claim-mine")
def claim_documents_bulk(
    body: ClaimBulkIn,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """Claim several shared documents as mine (from the scanner pool)."""
    documents = db.scalars(
        _visible_documents(user).where(Document.id.in_(body.document_ids))
    ).all()
    for document in documents:
        document.uploaded_by_user_id = user.id
        document.visibility = "private"
    db.commit()
    if documents:
        publish_event(user.company_id, "documents.changed", {"action": "claimed"})
    return {"claimed": len(documents)}


@router.post("/documents/{document_id}/claim", response_model=DocumentOut)
def claim_document(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """Take ownership of a shared/unowned document (marks it yours + private)."""
    document = _get_document(db, user, document_id)
    document.uploaded_by_user_id = user.id
    document.visibility = "private"
    db.commit()
    publish_event(user.company_id, "documents.changed", {"action": "claimed"})
    return document


@router.post("/documents/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    document = _get_document(db, user, document_id)
    if document.status == DocumentStatus.processing.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already processing")
    # Old pages are replaced wholesale; results history stays via ocr_results.
    for page in db.scalars(select(Page).where(Page.document_id == document.id)):
        db.delete(page)
    document.status = DocumentStatus.queued.value
    document.page_count = 0
    log_action(db, "document.reprocess", company_id=user.company_id, actor_user_id=user.id,
               target_type="document", target_id=str(document.id))
    db.commit()
    doc_service.enqueue_ocr(document, priority=9)
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    document = _get_document(db, user, document_id)
    db.delete(document)
    log_action(db, "document.delete", company_id=user.company_id, actor_user_id=user.id,
               target_type="document", target_id=str(document_id))
    db.commit()
    publish_event(user.company_id, "documents.changed", {"action": "deleted"})


@router.post("/documents/{document_id}/apply-template", response_model=DocumentOut)
def apply_template_to_document(
    document_id: uuid.UUID,
    template_id: uuid.UUID | None = None,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """Assign (or clear, when template_id omitted) a template and extract
    fields immediately from the stored OCR regions — no re-scan needed."""
    from app.services.extraction import apply_template

    document = _get_document(db, user, document_id)
    if template_id is not None:
        template = db.get(Template, template_id)
        if template is None or template.company_id != user.company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    apply_template(db, document, template_id)
    db.commit()
    publish_event(user.company_id, f"document.{document.id}.status", {"status": "updated"})
    return document


@router.patch("/documents/{document_id}/extracted", response_model=DocumentOut)
def update_extracted_values(
    document_id: uuid.UUID,
    values: dict[str, str | None],
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """Manual corrections to extracted field values (Fields tab edits)."""
    document = _get_document(db, user, document_id)
    if not document.extracted_json:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document has no extraction result")
    extracted = dict(document.extracted_json)
    fields = [dict(field) for field in extracted.get("fields", [])]
    for field in fields:
        if field["key"] in values:
            value = values[field["key"]]
            field["value"] = value
            field["missing"] = value is None or value == ""
            field["confidence"] = 1.0  # human-entered
    extracted["fields"] = fields
    document.extracted_json = extracted
    log_action(db, "document.extracted_edit", company_id=user.company_id, actor_user_id=user.id,
               target_type="document", target_id=str(document.id))
    db.commit()
    publish_event(user.company_id, f"document.{document.id}.status", {"status": "updated"})
    return document


@router.get("/documents/{document_id}/pages", response_model=list[PageOut])
def list_pages(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    document = _get_document(db, user, document_id)
    return db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()


@router.get("/documents/{document_id}/thumbnail")
def get_document_thumbnail(
    document_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    """First page image — used by the grid view. 404 until rasterization ran."""
    document = _get_document(db, user, document_id)
    first_page = db.scalar(
        select(Page)
        .where(Page.document_id == document.id)
        .order_by(Page.page_number)
        .limit(1)
    )
    if first_page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pages yet")
    return FileResponse(first_page.image_path, media_type="image/png")


@router.get("/pages/{page_id}/image")
def get_page_image(
    page_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    page = _get_page(db, user, page_id)
    return FileResponse(page.image_path, media_type="image/png")


@router.get("/pages/{page_id}/result", response_model=OcrResultOut)
def get_page_result(
    page_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    page = _get_page(db, user, page_id)
    result = db.scalar(
        select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No OCR result yet")
    return result


@router.get("/batches/{batch_id}", response_model=BatchOut)
def get_batch(
    batch_id: uuid.UUID,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    batch = db.get(Batch, batch_id)
    if batch is None or batch.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    return batch
