import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, select
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
    User,
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


def _get_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.company_id != user.company_id:
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
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
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
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(require_company_member),
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    query = select(Document).where(Document.company_id == user.company_id)
    if status_filter:
        query = query.where(Document.status == status_filter)
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if batch_id:
        query = query.where(Document.batch_id == batch_id)
    if q:
        query = query.where(Document.original_filename.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DocumentListOut(items=items, total=total, page=page, page_size=page_size)


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
    return path.read_text()


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
