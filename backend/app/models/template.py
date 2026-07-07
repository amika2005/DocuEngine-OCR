import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class Template(Base, UUIDMixin, TimestampMixin):
    """A company-defined OCR extraction template (請求書, 納品書, ...).

    `fields` defines what to pull out of the recognized text:
    [{key, label, description, type: text|date|number|amount, required: bool}]
    Documents scanned with a template get an extracted {key: value} result in
    addition to the normal markdown output.
    """

    __tablename__ = "templates"
    __table_args__ = (sa.UniqueConstraint("company_id", "name", name="uq_templates_name"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(sa.String(32), default="other", nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text)
    fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )
