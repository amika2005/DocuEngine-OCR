"""Add documents.visibility for per-user private/shared documents.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-13

"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent (see 0003/0004): the baseline creates it from the model.
    bind = op.get_bind()
    columns = [col["name"] for col in sa.inspect(bind).get_columns("documents")]
    if "visibility" not in columns:
        op.add_column(
            "documents",
            sa.Column("visibility", sa.String(length=16), server_default="shared", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("documents", "visibility")
