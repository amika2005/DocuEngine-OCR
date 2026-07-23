"""Add master_types.kind to separate product / client / supplier masters.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-22

"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent (see 0003/0004/0005): existing rows backfill to "other".
    bind = op.get_bind()
    columns = [col["name"] for col in sa.inspect(bind).get_columns("master_types")]
    if "kind" not in columns:
        op.add_column(
            "master_types",
            sa.Column("kind", sa.String(length=16), server_default="other", nullable=False),
        )
        op.create_index("ix_master_types_kind", "master_types", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_master_types_kind", table_name="master_types")
    op.drop_column("master_types", "kind")
