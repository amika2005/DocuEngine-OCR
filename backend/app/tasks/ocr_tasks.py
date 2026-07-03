"""The OCR pipeline: rasterize_document (cpu) → one ocr_page per page (gpu,
serialized) → assemble_document (cpu, chord callback).

Per-page granularity is what makes 100-document scanner batches safe on a single
GPU: the queue drains page by page, progress is fine-grained, and a failure
affects one page, never the batch."""

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from celery import chord
from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.events.publisher import publish_event
from app.models import (
    Batch,
    BatchStatus,
    Document,
    DocumentStatus,
    ModelVersion,
    ModelVersionStatus,
    OcrResult,
    Page,
    PageStatus,
)
from app.ocr import assemble
from app.ocr.engine import get_engine
from app.ocr.preprocess import rasterize
from app.services import storage
from app.tasks.celery_app import celery_app


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(bind=True, max_retries=2)
def rasterize_document(self, document_id: str) -> None:
    db = get_sessionmaker()()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            return
        document.status = DocumentStatus.processing.value
        db.commit()

        pages_dir = storage.document_dir(document.company_id, document.id) / "pages"
        rasterized = rasterize(Path(document.storage_path), pages_dir)

        page_ids: list[str] = []
        for rp in rasterized:
            page = Page(
                document_id=document.id,
                company_id=document.company_id,
                page_number=rp.page_number,
                image_path=str(rp.path),
                width_px=rp.width_px,
                height_px=rp.height_px,
                dpi=rp.dpi,
            )
            db.add(page)
            db.flush()
            page_ids.append(str(page.id))

        document.page_count = len(page_ids)
        document.queued_at = _utcnow()
        db.commit()

        publish_event(
            document.company_id,
            f"document.{document.id}.status",
            {"status": document.status, "page_count": len(page_ids)},
        )
        chord(
            [ocr_page.s(page_id) for page_id in page_ids],
            assemble_document.si(document_id),
        ).apply_async()
    except Exception as exc:
        db.rollback()
        _mark_document_failed(db, document_id, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2, soft_time_limit=180)
def ocr_page(self, page_id: str) -> None:
    db = get_sessionmaker()()
    try:
        page = db.get(Page, uuid.UUID(page_id))
        if page is None:
            return
        page.status = PageStatus.processing.value
        db.commit()

        started = time.monotonic()
        try:
            result = get_engine().parse_page(Path(page.image_path))
        except Exception as exc:
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=5 * (self.request.retries + 1))
            # Final failure: keep the reason so the UI can show WHY, not just a
            # bare "failed" — engine misconfiguration must be self-diagnosable.
            logger.exception("OCR failed for page %s", page_id)
            page.status = PageStatus.failed.value
            page.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
            _publish_page_event(db, page)
            return

        elapsed_ms = int((time.monotonic() - started) * 1000)
        engine = get_engine()

        db.execute(
            OcrResult.__table__.update()
            .where(OcrResult.page_id == page.id, OcrResult.is_current)
            .values(is_current=False)
        )
        db.add(
            OcrResult(
                page_id=page.id,
                company_id=page.company_id,
                model_version_id=_active_model_version_id(db, page.company_id),
                markdown=assemble.page_markdown(result),
                layout_json={
                    "regions": [
                        {
                            "bbox": list(r.bbox),
                            "kind": r.kind,
                            "markdown": r.markdown,
                            "confidence": r.confidence,
                            "vertical": r.vertical,
                        }
                        for r in result.regions
                    ]
                },
                avg_confidence=result.avg_confidence,
                engine=engine.name,
                is_current=True,
            )
        )
        page.status = PageStatus.completed.value
        page.processing_ms = elapsed_ms
        db.commit()
        _publish_page_event(db, page)
    finally:
        db.close()


@celery_app.task
def assemble_document(document_id: str) -> None:
    db = get_sessionmaker()()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            return

        pages = db.scalars(
            select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
        ).all()
        failed = [p for p in pages if p.status != PageStatus.completed.value]

        page_markdowns: list[str] = []
        for page in pages:
            result = db.scalar(
                select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
            )
            if result:
                page_markdowns.append(result.markdown)
            else:
                reason = page.error_message or "unknown error"
                page_markdowns.append(f"<!-- page {page.page_number}: OCR failed — {reason} -->")

        md_path = storage.document_markdown_path(document.company_id, document.id)
        storage.save_bytes(md_path, assemble.document_markdown(page_markdowns).encode())

        document.status = (
            DocumentStatus.partially_failed.value if failed else DocumentStatus.completed.value
        )
        if failed:
            document.error_message = (
                f"{len(failed)}/{len(pages)} pages failed — "
                + (failed[0].error_message or "see worker logs")
            )[:2000]
        document.model_version_id = _active_model_version_id(db, document.company_id)
        document.completed_at = _utcnow()
        db.commit()

        _bump_batch(db, document)
        publish_event(
            document.company_id,
            f"document.{document.id}.status",
            {"status": document.status, "failed_pages": len(failed)},
        )
        match_masters.apply_async(args=[document_id])
    finally:
        db.close()


@celery_app.task
def match_masters(document_id: str) -> None:
    """Post-OCR: compare page markdown against the tenant's master data and
    store suggested matches (green tick / amber tilde in the UI)."""
    from app.services.matching import match_document

    db = get_sessionmaker()()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            return
        created = match_document(db, document)
        publish_event(
            document.company_id,
            "matches.changed",
            {"document_id": document_id, "suggested": created},
        )
    finally:
        db.close()


def _active_model_version_id(db, company_id: uuid.UUID) -> uuid.UUID | None:
    """Tenant adapter wins over the global base model."""
    for scope in (company_id, None):
        version = db.scalar(
            select(ModelVersion).where(
                ModelVersion.company_id == scope,
                ModelVersion.status == ModelVersionStatus.active.value,
            )
        )
        if version:
            return version.id
    return None


def _publish_page_event(db, page: Page) -> None:
    total = db.scalar(select(Document.page_count).where(Document.id == page.document_id))
    done = db.scalar(
        select(func.count())
        .select_from(Page)
        .where(
            Page.document_id == page.document_id,
            Page.status.in_([PageStatus.completed.value, PageStatus.failed.value]),
        )
    )
    publish_event(
        page.company_id,
        f"document.{page.document_id}.progress",
        {"pages_done": done, "pages_total": total, "page": page.page_number, "status": page.status},
    )


def _bump_batch(db, document: Document) -> None:
    if document.batch_id is None:
        return
    batch = db.get(Batch, document.batch_id)
    if batch is None:
        return
    batch.completed_documents += 1
    if batch.completed_documents >= batch.total_documents and batch.status != BatchStatus.open.value:
        batch.status = BatchStatus.completed.value
    db.commit()
    publish_event(
        document.company_id,
        f"batch.{batch.id}.progress",
        {"completed": batch.completed_documents, "total": batch.total_documents},
    )


def _mark_document_failed(db, document_id: str, error: str) -> None:
    document = db.get(Document, uuid.UUID(document_id))
    if document is None:
        return
    document.status = DocumentStatus.failed.value
    document.error_message = error[:2000]
    db.commit()
    publish_event(
        document.company_id, f"document.{document.id}.status", {"status": document.status}
    )
