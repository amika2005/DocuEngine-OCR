"""Add pages.error_message so per-page OCR failures carry their reason.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03

"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the 0001 baseline creates tables from the current models, so
    # on a fresh install this column may already exist. Only add it when the DB
    # was created from an older baseline that predated it.
    bind = op.get_bind()
    columns = [col["name"] for col in sa.inspect(bind).get_columns("pages")]
    if "error_message" not in columns:
        op.add_column("pages", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "error_message")
