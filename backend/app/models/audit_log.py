import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.company import JSONB


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Insert-only audit trail: logins, admin actions, uploads, model promotions."""

    __tablename__ = "audit_logs"
    __table_args__ = (sa.Index("ix_audit_logs_company_created", "company_id", "created_at"),)

    company_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    actor_device_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    action: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(sa.String(64))
    target_id: Mapped[str | None] = mapped_column(sa.String(64))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ip: Mapped[str | None] = mapped_column(sa.String(64))
