import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class CorrectionStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    used_in_training = "used_in_training"


class Correction(Base, UUIDMixin, TimestampMixin):
    """A user's fix of OCR output. Approved corrections become fine-tuning pairs:
    (page image, corrected_markdown) with ocr_result_id pinning the source model."""

    __tablename__ = "corrections"
    __table_args__ = (sa.Index("ix_corrections_company_status", "company_id", "status"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("pages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ocr_result_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("ocr_results.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    original_markdown: Mapped[str] = mapped_column(sa.Text, nullable=False)
    corrected_markdown: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # NULL = whole-page correction; otherwise index into layout_json regions
    region_index: Mapped[int | None] = mapped_column(sa.Integer)
    status: Mapped[str] = mapped_column(
        sa.String(32), default=CorrectionStatus.draft.value, nullable=False
    )
    training_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("training_runs.id", ondelete="SET NULL")
    )
