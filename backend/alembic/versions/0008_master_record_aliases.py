"""Add master_records.aliases — learned OCR spellings that map to a record.

When a user links a fuzzy match, the confirmed OCR text is stored here so the
same text auto-links to the canonical master value next time (no re-confirming).

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = [col["name"] for col in sa.inspect(bind).get_columns("master_records")]
    if "aliases" in columns:
        return
    # JSONB on Postgres, JSON elsewhere; existing rows backfill to an empty list.
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column(
        "master_records",
        sa.Column("aliases", json_type, server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("master_records", "aliases")
