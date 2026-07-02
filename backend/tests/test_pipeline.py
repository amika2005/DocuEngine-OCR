"""End-to-end pipeline test: a generated Japanese-invoice PDF runs through
rasterize → ocr_page (mock engine) → assemble with eager Celery, producing
markdown with tables and correct statuses."""

import io
import uuid

import fitz
import pytest
from sqlalchemy import select

from app.models import Document, DocumentStatus, OcrResult, Page, PageStatus
from app.services import documents as doc_service
from app.services import storage
from app.tasks.celery_app import celery_app
from app.tasks import ocr_tasks


@pytest.fixture(scope="module", autouse=True)
def eager_celery():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


def make_pdf(pages: int = 2) -> bytes:
    pdf = fitz.open()
    for number in range(pages):
        page = pdf.new_page()
        page.insert_text((72, 72), f"INVOICE page {number + 1}")
    return pdf.tobytes()


def test_pdf_flows_to_completed_markdown(db, seed):
    company = seed["company_a"]
    document = doc_service.create_document(
        db,
        company_id=company.id,
        filename="pipeline-invoice.pdf",
        content=make_pdf(pages=2),
        uploaded_by_user_id=seed["user_a"].id,
    )

    ocr_tasks.rasterize_document.apply(args=[str(document.id)]).get()

    db.expire_all()
    refreshed = db.get(Document, document.id)
    assert refreshed.status == DocumentStatus.completed.value
    assert refreshed.page_count == 2
    assert refreshed.completed_at is not None

    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()
    assert [page.status for page in pages] == [PageStatus.completed.value] * 2
    assert all(page.processing_ms is not None for page in pages)

    for page in pages:
        result = db.scalar(
            select(OcrResult).where(OcrResult.page_id == page.id, OcrResult.is_current)
        )
        assert result is not None
        assert "請求書" in result.markdown  # mock engine emits invoice-shaped JA markdown
        assert result.layout_json["regions"]

    markdown = storage.document_markdown_path(company.id, document.id).read_text()
    assert markdown.count("| 品目 |") == 2  # one table per page
    assert "\n\n---\n\n" in markdown  # page separator


def test_failed_rasterize_marks_document_failed(db, seed):
    document = doc_service.create_document(
        db,
        company_id=seed["company_a"].id,
        filename="corrupt.pdf",
        content=b"%PDF-1.4 this is not really a pdf",
        uploaded_by_user_id=seed["user_a"].id,
    )
    with pytest.raises(Exception):
        ocr_tasks.rasterize_document.apply(args=[str(document.id)], throw=True).get()

    db.expire_all()
    refreshed = db.get(Document, document.id)
    assert refreshed.status == DocumentStatus.failed.value
    assert refreshed.error_message


def test_image_input_is_rasterized_like_pdf(db, seed):
    pdf = fitz.open()
    page = pdf.new_page(width=400, height=300)
    page.insert_text((36, 36), "scan")
    pixmap = page.get_pixmap()
    png_bytes = pixmap.tobytes("png")

    document = doc_service.create_document(
        db,
        company_id=seed["company_a"].id,
        filename="scan.png",
        content=png_bytes,
        uploaded_by_user_id=seed["user_a"].id,
    )
    ocr_tasks.rasterize_document.apply(args=[str(document.id)]).get()

    db.expire_all()
    refreshed = db.get(Document, document.id)
    assert refreshed.status == DocumentStatus.completed.value
    assert refreshed.page_count == 1
