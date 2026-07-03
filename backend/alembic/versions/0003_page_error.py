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
    op.add_column("pages", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "error_message")
