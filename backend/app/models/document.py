import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class DocType(str, enum.Enum):
    invoice = "invoice"
    tax_report = "tax_report"
    quotation = "quotation"
    letter = "letter"
    other = "other"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    partially_failed = "partially_failed"


class BatchStatus(str, enum.Enum):
    open = "open"
    processing = "processing"
    completed = "completed"


class Batch(Base, UUIDMixin, TimestampMixin):
    """Groups documents from one scanner run so the UI can show batch progress."""

    __tablename__ = "batches"

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("devices.id", ondelete="SET NULL")
    )
    total_documents: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    completed_documents: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), default=BatchStatus.open.value, nullable=False)


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        # Dedup is scoped to the uploader in application code (see
        # services/documents.create_document), so this is a plain lookup index,
        # not a company-wide UNIQUE — otherwise one user's copy would block
        # another user in the same company from scanning the same file.
        sa.Index("ix_documents_company_sha", "company_id", "content_sha256"),
        sa.Index("ix_documents_company_status", "company_id", "status"),
        sa.Index("ix_documents_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_by_user = relationship("User", foreign_keys=[uploaded_by_user_id], lazy="joined")
    uploaded_by_device_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("devices.id", ondelete="SET NULL")
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("batches.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    page_count: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    doc_type: Mapped[str] = mapped_column(sa.String(32), default=DocType.other.value, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("templates.id", ondelete="SET NULL"), index=True
    )
    # Field extraction output when a template is assigned:
    # {template_name, fields: [{key,label,type,required,value,confidence,page_number,bbox,missing}]}
    extracted_json: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        sa.String(32), default=DocumentStatus.uploaded.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    # private = owner (uploaded_by_user_id) + company admins only;
    # shared = every company member. Device/scanner uploads default to shared.
    visibility: Mapped[str] = mapped_column(sa.String(16), default="shared", nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    queued_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
