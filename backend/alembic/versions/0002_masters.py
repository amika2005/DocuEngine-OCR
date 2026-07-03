"""Master data: master_types, master_records, master_matches.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03

"""
from alembic import op

import app.models  # noqa: F401  — register all tables on Base.metadata
from app.db.base import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_TABLES = ["master_types", "master_records", "master_matches"]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind, tables=[Base.metadata.tables[name] for name in _TABLES]
    )


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(_TABLES):
        Base.metadata.tables[name].drop(bind=bind)
