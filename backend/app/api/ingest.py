"""Watcher-app ingestion. Authenticated by X-Device-Token. Uploads are
idempotent by content hash, so the watcher can retry forever without creating
duplicates, and 429 backpressure tells it to slow down when the queue is deep."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_device
from app.config import get_settings
from app.db.session import get_db
from app.models import Batch, BatchStatus, Device, Document, DocumentStatus, Page, PageStatus
from app.schemas.document import BatchOut, DocumentOut
from app.services import documents as doc_service

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/handshake")
def handshake(device: Device = Depends(get_current_device), db: Session = Depends(get_db)):
    return {
        "device_id": str(device.id),
        "device_name": device.name,
        "company_id": str(device.company_id),
        "allowed_extensions": sorted(doc_service.ALLOWED_SUFFIXES),
    }


@router.post("/batches", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def open_batch(device: Device = Depends(get_current_device), db: Session = Depends(get_db)):
    batch = Batch(company_id=device.company_id, device_id=device.id)
    db.add(batch)
    db.commit()
    return batch


@router.post("/batches/{batch_id}/close", response_model=BatchOut)
def close_batch(
    batch_id: uuid.UUID,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    batch = db.get(Batch, batch_id)
    if batch is None or batch.company_id != device.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
    if batch.status == BatchStatus.open.value:
        batch.status = (
            BatchStatus.completed.value
            if batch.completed_documents >= batch.total_documents
            else BatchStatus.processing.value
        )
        db.commit()
    return batch


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    file: UploadFile,
    batch_id: uuid.UUID | None = None,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    # Backpressure: if too many pages are waiting, tell the watcher to retry later.
    pending = db.scalar(
        select(func.count())
        .select_from(Page)
        .where(
            Page.company_id == device.company_id,
            Page.status == PageStatus.pending.value,
        )
    )
    if pending and pending > get_settings().ingest_max_queue_depth:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "OCR queue is full; retry later",
            headers={"Retry-After": "60"},
        )

    if batch_id is not None:
        batch = db.get(Batch, batch_id)
        if batch is None or batch.company_id != device.company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")

    content = await file.read()
    try:
        document = doc_service.create_document(
            db,
            company_id=device.company_id,
            filename=file.filename or "scan.bin",
            content=content,
            uploaded_by_device_id=device.id,
            batch_id=batch_id,
        )
    except doc_service.DuplicateDocumentError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "Duplicate document", "existing_id": str(exc.existing_id)},
        )
    except doc_service.UnsupportedFileTypeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))

    if batch_id is not None:
        db.execute(
            Batch.__table__.update()
            .where(Batch.id == batch_id)
            .values(total_documents=Batch.total_documents + 1)
        )
        db.commit()

    doc_service.enqueue_ocr(document)
    return document


@router.get("/documents/{document_id}/status")
def document_status(
    document_id: uuid.UUID,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if document is None or document.company_id != device.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return {"id": str(document.id), "status": document.status, "page_count": document.page_count}
