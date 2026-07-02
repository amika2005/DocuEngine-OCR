import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class ModelKind(str, enum.Enum):
    base = "base"
    lora_adapter = "lora_adapter"
    rec_finetune = "rec_finetune"


class ModelVersionStatus(str, enum.Enum):
    training = "training"
    evaluating = "evaluating"
    candidate = "candidate"
    active = "active"
    rejected = "rejected"
    retired = "retired"


class ModelVersion(Base, UUIDMixin, TimestampMixin):
    """Registry of OCR model artifacts. company_id NULL = global base model;
    otherwise a per-tenant fine-tuned adapter. At most one active per (company, kind)."""

    __tablename__ = "model_versions"
    __table_args__ = (
        sa.Index(
            "uq_model_versions_active",
            "company_id",
            "kind",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        ),
    )

    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    artifact_path: Mapped[str | None] = mapped_column(sa.String(1024))
    artifact_sha256: Mapped[str | None] = mapped_column(sa.String(64))
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
