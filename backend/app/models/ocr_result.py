import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class OcrResult(Base, UUIDMixin, TimestampMixin):
    """One OCR pass over one page. History is kept: re-processing with a new model
    inserts a new row and flips is_current, so results can always be compared."""

    __tablename__ = "ocr_results"
    __table_args__ = (
        sa.Index(
            "uq_ocr_results_current_page",
            "page_id",
            unique=True,
            postgresql_where=sa.text("is_current"),
            sqlite_where=sa.text("is_current"),
        ),
    )

    page_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("pages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    markdown: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # regions: [{bbox: [x0,y0,x1,y1], kind: text|table|figure|title|handwriting,
    #            markdown: str, confidence: float, vertical: bool}]
    layout_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    avg_confidence: Mapped[float | None] = mapped_column(sa.Float)
    engine: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    is_current: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)
