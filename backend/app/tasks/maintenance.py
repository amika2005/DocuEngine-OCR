"""Scheduled housekeeping + the nightly training trigger. The actual fine-tune
runs in the separate trainer container (queue `training`); this task only decides
whether tonight's window should fire, per tenant."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Company, Correction, CorrectionStatus, Document, DocumentStatus
from app.tasks.celery_app import celery_app


@celery_app.task
def maybe_start_training() -> None:
    settings = get_settings()
    if not settings.training_enabled:
        return
    db = get_sessionmaker()()
    try:
        companies = db.scalars(select(Company).where(Company.status == "active")).all()
        for company in companies:
            if not company.settings.get("training_enabled", True):
                continue
            unused = db.scalar(
                select(func.count())
                .select_from(Correction)
                .where(
                    Correction.company_id == company.id,
                    Correction.status == CorrectionStatus.approved.value,
                )
            )
            if unused and unused >= settings.training_min_corrections:
                # Consumed by the trainer container.
                celery_app.send_task(
                    "trainer.run_training", args=[str(company.id)], queue="training"
                )
    finally:
        db.close()


@celery_app.task
def cleanup_stale_uploads() -> None:
    """Documents stuck in `uploaded` for over a day (e.g. worker died before
    queueing) are marked failed so users see the truth instead of a spinner."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    db = get_sessionmaker()()
    try:
        stale = db.scalars(
            select(Document).where(
                Document.status == DocumentStatus.uploaded.value,
                Document.created_at < cutoff,
            )
        ).all()
        for document in stale:
            document.status = DocumentStatus.failed.value
            document.error_message = "stale: never entered the OCR queue"
        db.commit()
    finally:
        db.close()
