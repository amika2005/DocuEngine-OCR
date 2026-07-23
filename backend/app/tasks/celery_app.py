from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "docuengine",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.ocr_tasks", "app.tasks.maintenance"],
)

from celery.signals import worker_ready  # noqa: E402


@worker_ready.connect
def _requeue_stuck_documents(sender=None, **kwargs):
    """Self-heal on worker start: any document still queued/processing after
    5 minutes lost its tasks (worker died, machine rebooted, …) — reset it and
    run the pipeline again so nothing stays stuck forever."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.db.session import get_sessionmaker
    from app.models import Document, DocumentStatus, Page
    from app.tasks.ocr_tasks import rasterize_document

    db = get_sessionmaker()()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        stuck = db.scalars(
            select(Document).where(
                Document.status.in_(
                    [DocumentStatus.queued.value, DocumentStatus.processing.value]
                ),
                Document.created_at < cutoff,
            )
        ).all()
        for document in stuck:
            for page in db.scalars(select(Page).where(Page.document_id == document.id)):
                db.delete(page)
            document.status = DocumentStatus.queued.value
            document.page_count = 0
        db.commit()
        for document in stuck:
            rasterize_document.apply_async(args=[str(document.id)], priority=5)
    except Exception:  # never block worker startup on the self-heal pass
        db.rollback()
    finally:
        db.close()


celery_app.conf.update(
    # A crashed worker re-delivers at most one in-flight page.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="cpu",
    task_routes={
        "app.tasks.ocr_tasks.ocr_page": {"queue": "ocr_gpu"},
        "app.tasks.ocr_tasks.rasterize_document": {"queue": "cpu"},
        "app.tasks.ocr_tasks.assemble_document": {"queue": "cpu"},
        "app.tasks.ocr_tasks.match_masters": {"queue": "cpu"},
        "app.tasks.maintenance.*": {"queue": "cpu"},
        "trainer.*": {"queue": "training"},
    },
    # Interactive re-OCR jumps ahead of bulk scanner batches. A killed
    # worker's unacked task is re-delivered after visibility_timeout seconds
    # (matches ocr_page's soft_time_limit) instead of Redis's 1-hour default.
    broker_transport_options={"priority_steps": [0, 5, 9], "visibility_timeout": 600},
    timezone="Asia/Tokyo",
    beat_schedule={
        "weekly-training-window": {
            "task": "app.tasks.maintenance.maybe_start_training",
            "schedule": crontab(
                hour=settings.training_schedule_hour_jst,
                minute=0,
                day_of_week=settings.training_schedule_day_of_week,
            ),
        },
        "hourly-cleanup": {
            "task": "app.tasks.maintenance.cleanup_stale_uploads",
            "schedule": crontab(minute=15),
        },
    },
)
