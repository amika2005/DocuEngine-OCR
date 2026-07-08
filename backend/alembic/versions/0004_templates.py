"""OCR extraction templates: templates table + documents.template_id/extracted_json.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

"""
import sqlalchemy as sa
from alembic import op

import app.models  # noqa: F401  — register all tables on Base.metadata
from app.db.base import Base
from app.models.company import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the 0001 baseline creates tables/columns from the current
    # models, so on a fresh install these may already exist. Only apply what's
    # missing (for DBs created from an older baseline). create_all already
    # skips existing tables via checkfirst.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables["templates"]])
    inspector = sa.inspect(bind)
    doc_columns = [col["name"] for col in inspector.get_columns("documents")]
    if "template_id" not in doc_columns:
        op.add_column(
            "documents",
            sa.Column("template_id", sa.Uuid(), sa.ForeignKey("templates.id", ondelete="SET NULL")),
        )
        op.create_index("ix_documents_template_id", "documents", ["template_id"])
    if "extracted_json" not in doc_columns:
        op.add_column("documents", sa.Column("extracted_json", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "extracted_json")
    op.drop_index("ix_documents_template_id", "documents")
    op.drop_column("documents", "template_id")
    Base.metadata.tables["templates"].drop(bind=op.get_bind())
