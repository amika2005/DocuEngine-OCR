import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin

JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class Company(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    name_kana: Mapped[str | None] = mapped_column(sa.String(255))
    slug: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), default="active", nullable=False)
    # settings: dpi, retention_days, training_enabled, require_correction_approval
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    max_users: Mapped[int] = mapped_column(sa.Integer, default=50, nullable=False)
    max_devices: Mapped[int] = mapped_column(sa.Integer, default=10, nullable=False)
