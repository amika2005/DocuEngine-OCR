import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class MasterKind(str, enum.Enum):
    """What a master type represents, so product/client/supplier lists can be
    shown and grouped separately in the UI."""

    product = "product"
    client = "client"
    supplier = "supplier"
    other = "other"


class MasterType(Base, UUIDMixin, TimestampMixin):
    """A company-defined master data category (得意先, 商品, 仕入先, ...).
    `fields` defines the record schema:
    [{key, label, matchable: bool, required: bool}] — only matchable fields are
    compared against OCR output."""

    __tablename__ = "master_types"
    __table_args__ = (sa.UniqueConstraint("company_id", "name", name="uq_master_types_name"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    kind: Mapped[str] = mapped_column(
        sa.String(16), default=MasterKind.other.value, server_default="other",
        nullable=False, index=True,
    )
    fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )


class MasterRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "master_records"
    __table_args__ = (sa.Index("ix_master_records_company_type", "company_id", "master_type_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    master_type_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("master_types.id", ondelete="CASCADE"), nullable=False
    )
    # {field_key: value}
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Confirmed OCR spellings/misreads that resolve to this record, learned when
    # a user links a fuzzy match. Each entry: {"field_key": str, "text": str}.
    # Future OCR of the same text auto-links to the canonical value with no
    # re-confirmation — this is how the system "learns" a company's product and
    # client names from corrections.
    aliases: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )


class MatchKind(str, enum.Enum):
    exact = "exact"
    fuzzy = "fuzzy"


class MatchStatus(str, enum.Enum):
    suggested = "suggested"
    linked = "linked"
    dismissed = "dismissed"


class MasterMatch(Base, UUIDMixin, TimestampMixin):
    """A detected correspondence between OCR text on a page and a master-record
    field value. `linked` means a user confirmed it — the OCR text was replaced
    by the master value and an approved Correction was recorded."""

    __tablename__ = "master_matches"
    __table_args__ = (
        sa.Index("ix_master_matches_company_page", "company_id", "page_id", "status"),
        sa.UniqueConstraint(
            "ocr_result_id",
            "master_record_id",
            "field_key",
            "matched_text",
            name="uq_master_matches_dedupe",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("pages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ocr_result_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("ocr_results.id", ondelete="CASCADE"), nullable=False
    )
    master_record_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("master_records.id", ondelete="CASCADE"), nullable=False
    )
    master_type_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("master_types.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    matched_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    master_value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), default=MatchStatus.suggested.value, nullable=False
    )
    linked_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    linked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
