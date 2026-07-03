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
    # Interactive re-OCR jumps ahead of bulk scanner batches.
    broker_transport_options={"priority_steps": [0, 5, 9]},
    timezone="Asia/Tokyo",
    beat_schedule={
        "nightly-training-window": {
            "task": "app.tasks.maintenance.maybe_start_training",
            "schedule": crontab(hour=settings.training_schedule_hour_jst, minute=0),
        },
        "hourly-cleanup": {
            "task": "app.tasks.maintenance.cleanup_stale_uploads",
            "schedule": crontab(minute=15),
        },
    },
)
