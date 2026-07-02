"""The trainer worker: consumes `trainer.run_training` from the `training`
queue. Owns the GPU during a run by pausing the OCR worker's queue consumption;
OCR jobs simply pile up in Redis and drain afterwards."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import Celery
from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.models import (
    Correction,
    CorrectionStatus,
    ModelVersion,
    ModelVersionStatus,
    TrainingRun,
    TrainingRunStatus,
)
from trainer import dataset as dataset_module
from trainer.evaluate import EvalReport, apply_gate
from trainer.finetune_rec import train_rec_model
from trainer.finetune_vl_lora import LoraTrainingError, train_lora_adapter
from trainer.promote import register_candidate

settings = get_settings()

celery_app = Celery("docuengine-trainer", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, timezone="Asia/Tokyo")

OCR_QUEUE = "ocr_gpu"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pause_ocr_workers() -> None:
    celery_app.control.cancel_consumer(OCR_QUEUE, reply=False)


def _resume_ocr_workers() -> None:
    celery_app.control.add_consumer(OCR_QUEUE, reply=False)


@celery_app.task(name="trainer.run_training")
def run_training(company_id: str, training_run_id: str | None = None) -> None:
    db = get_sessionmaker()()
    company_uuid = uuid.UUID(company_id)
    try:
        if training_run_id:
            run = db.get(TrainingRun, uuid.UUID(training_run_id))
        else:
            run = TrainingRun(company_id=company_uuid, triggered_by="schedule")
            db.add(run)
        run.status = TrainingRunStatus.preparing_data.value
        run.started_at = _utcnow()
        db.commit()

        run_dir = settings.data_dir / "training" / str(run.id)
        run.log_path = str(run_dir / "train.log")

        stats = dataset_module.build_dataset(db, company_uuid, run_dir)
        run.dataset_stats = stats.as_dict()
        if stats.train_pairs == 0:
            run.status = TrainingRunStatus.error.value
            run.eval_report = {"reason": "no approved corrections to train on"}
            run.finished_at = _utcnow()
            db.commit()
            return

        base = db.scalar(
            select(ModelVersion).where(
                ModelVersion.company_id.is_(None),
                ModelVersion.kind == "base",
                ModelVersion.status == ModelVersionStatus.active.value,
            )
        )
        run.base_model_version_id = base.id if base else None
        run.status = TrainingRunStatus.training.value
        db.commit()

        backend = os.environ.get("TRAINER_BACKEND", "vl_lora")
        train_fn = train_rec_model if backend == "rec" else train_lora_adapter
        adapter_dir = run_dir / "adapter"

        _pause_ocr_workers()
        try:
            train_fn(
                base_model_dir=Path(base.artifact_path) if base and base.artifact_path else settings.models_dir,
                train_jsonl=run_dir / "train.jsonl",
                output_dir=adapter_dir,
                wall_clock_limit_s=settings.training_wall_clock_hours * 3600,
            )

            run.status = TrainingRunStatus.evaluating.value
            db.commit()
            report = _evaluate(run_dir)
            run.eval_report = report.as_dict()

            version = register_candidate(db, run, company_uuid, adapter_dir, report)
            run.status = (
                TrainingRunStatus.passed.value
                if report.passed
                else TrainingRunStatus.failed_gate.value
            )
            if report.passed:
                _mark_corrections_used(db, stats.correction_ids, run.id)
            _ = version
        finally:
            _resume_ocr_workers()

        run.finished_at = _utcnow()
        db.commit()
    except LoraTrainingError as exc:
        db.rollback()
        _record_error(db, run.id if run else None, str(exc))
    except Exception as exc:  # never leave a run dangling in `training`
        db.rollback()
        _record_error(db, run.id if run else None, f"unexpected: {exc}")
        raise
    finally:
        db.close()


def _evaluate(run_dir: Path) -> EvalReport:
    """Runs baseline vs candidate over holdout + golden set.

    Full model-in-the-loop evaluation (re-OCR the holdout images with both
    models) plugs in here once a training backend is wired up; until then the
    gate is exercised end-to-end by the test suite via synthetic reports."""
    raise LoraTrainingError("evaluation requires a wired-up training backend")


def _mark_corrections_used(db, correction_ids: list[str], run_id: uuid.UUID) -> None:
    for correction_id in correction_ids:
        correction = db.get(Correction, uuid.UUID(correction_id))
        if correction is not None:
            correction.status = CorrectionStatus.used_in_training.value
            correction.training_run_id = run_id


def _record_error(db, run_id: uuid.UUID | None, message: str) -> None:
    if run_id is None:
        return
    run = db.get(TrainingRun, run_id)
    if run is None:
        return
    run.status = TrainingRunStatus.error.value
    run.eval_report = {**(run.eval_report or {}), "error": message}
    run.finished_at = _utcnow()
    db.commit()
