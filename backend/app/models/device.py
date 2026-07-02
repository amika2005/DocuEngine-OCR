import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Device(Base, UUIDMixin, TimestampMixin):
    """A watcher installation (scanner PC). Authenticates with a long-lived token,
    shown in plaintext exactly once at creation and stored only as a sha256 hash."""

    __tablename__ = "devices"

    company_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), default="active", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")
    )
