"""Drop the company-wide unique on (company_id, content_sha256).

Dedup is now scoped to the uploader in application code so that one user's
copy (often a private document) no longer blocks another user in the same
company from scanning the same file. The unique constraint is replaced by a
plain lookup index.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23

"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # SQLite can't ALTER ... DROP CONSTRAINT; production runs on Postgres and
    # the test suite builds its schema from metadata (not migrations).
    if bind.dialect.name != "sqlite":
        uniques = {uc["name"] for uc in insp.get_unique_constraints("documents")}
        if "uq_documents_company_sha" in uniques:
            op.drop_constraint("uq_documents_company_sha", "documents", type_="unique")

    indexes = {ix["name"] for ix in insp.get_indexes("documents")}
    if "ix_documents_company_sha" not in indexes:
        op.create_index(
            "ix_documents_company_sha", "documents", ["company_id", "content_sha256"]
        )


def downgrade() -> None:
    op.drop_index("ix_documents_company_sha", table_name="documents")
    op.create_unique_constraint(
        "uq_documents_company_sha", "documents", ["company_id", "content_sha256"]
    )
