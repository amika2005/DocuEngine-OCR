import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    company_admin = "company_admin"
    user = "user"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    # NULL for super admins (Sonasu staff are not tied to a tenant)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[str] = mapped_column(sa.String(32), default=UserRole.user.value, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
