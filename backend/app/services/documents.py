"""Shared document intake used by both the web upload endpoint and the watcher
ingest endpoint: dedupe by content hash, persist the original, queue OCR."""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentStatus
from app.services import storage

ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class DuplicateDocumentError(Exception):
    def __init__(self, existing_id: uuid.UUID):
        self.existing_id = existing_id


class UnsupportedFileTypeError(Exception):
    pass


def create_document(
    db: Session,
    *,
    company_id: uuid.UUID,
    filename: str,
    content: bytes,
    uploaded_by_user_id: uuid.UUID | None = None,
    uploaded_by_device_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    doc_type: str = "other",
) -> Document:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UnsupportedFileTypeError(f"unsupported file type: {suffix or '(none)'}")

    # Duplicate detection is scoped to the uploader, not the whole company:
    # each person (and each device) has their own dedup namespace. This stops a
    # user being blocked as a "duplicate" by someone else's copy — often a
    # private document they can't even see — while still catching a person (or
    # the watcher) re-uploading the exact same file.
    sha256 = storage.sha256_bytes(content)
    conditions = [
        Document.company_id == company_id,
        Document.content_sha256 == sha256,
    ]
    if uploaded_by_user_id is not None:
        conditions.append(Document.uploaded_by_user_id == uploaded_by_user_id)
    elif uploaded_by_device_id is not None:
        conditions.append(Document.uploaded_by_device_id == uploaded_by_device_id)
    existing = db.scalar(select(Document).where(*conditions))
    if existing is not None:
        raise DuplicateDocumentError(existing.id)

    document = Document(
        company_id=company_id,
        uploaded_by_user_id=uploaded_by_user_id,
        uploaded_by_device_id=uploaded_by_device_id,
        batch_id=batch_id,
        original_filename=filename,
        content_sha256=sha256,
        mime_type=MIME_BY_SUFFIX[suffix],
        byte_size=len(content),
        storage_path="",
        doc_type=doc_type,
        status=DocumentStatus.uploaded.value,
    )
    db.add(document)
    db.flush()

    path = storage.original_path(company_id, document.id, filename)
    storage.save_bytes(path, content)
    document.storage_path = str(path)
    document.status = DocumentStatus.queued.value
    db.commit()
    return document


def enqueue_ocr(document: Document, priority: int = 0) -> None:
    from app.tasks.ocr_tasks import rasterize_document

    rasterize_document.apply_async(args=[str(document.id)], priority=priority)
