import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class TrainingRunStatus(str, enum.Enum):
    pending = "pending"
    preparing_data = "preparing_data"
    training = "training"
    evaluating = "evaluating"
    passed = "passed"
    failed_gate = "failed_gate"
    error = "error"
    cancelled = "cancelled"


class TrainingRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "training_runs"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    base_model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    produced_model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        sa.String(32), default=TrainingRunStatus.pending.value, nullable=False
    )
    dataset_stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    eval_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    log_path: Mapped[str | None] = mapped_column(sa.String(1024))
    triggered_by: Mapped[str] = mapped_column(sa.String(32), default="schedule", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
