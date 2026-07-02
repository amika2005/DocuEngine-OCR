import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class PageStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Page(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "pages"
    __table_args__ = (
        sa.UniqueConstraint("document_id", "page_number", name="uq_pages_document_number"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # denormalized for tenant scoping without a join
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    width_px: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    height_px: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    dpi: Mapped[int] = mapped_column(sa.Integer, default=200, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), default=PageStatus.pending.value, nullable=False
    )
    processing_ms: Mapped[int | None] = mapped_column(sa.Integer)
