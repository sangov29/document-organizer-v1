"""race-safe document version numbering

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_document_version_group_number"


def upgrade():
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("documents")}
    if INDEX_NAME in indexes:
        return

    # Fresh-install-safe AND duplicate-safe: before the unique index can be
    # created, densely renumber version_number within each complete logical
    # group. COALESCE(version_group_id, id) is also the API's grouping rule:
    # it includes the root row (whose group is its own id) together with all
    # later versions. This preserves a valid 1,2,3 history and repairs any
    # pre-fix collision deterministically. Historical version numbers can be
    # changed only where a collision/gap makes repair necessary; stable IDs
    # and predecessor lineage remain authoritative.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(version_group_id, id)
                ORDER BY version_number, uploaded_at, id
            ) AS rn
            FROM documents
        )
        UPDATE documents
        SET version_number = ranked.rn
        FROM ranked
        WHERE documents.id = ranked.id
          AND documents.version_number IS DISTINCT FROM ranked.rn
        """
    )

    op.execute(
        "CREATE UNIQUE INDEX uq_document_version_group_number "
        "ON documents ((COALESCE(version_group_id, id)), version_number)"
    )


def downgrade():
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("documents")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="documents")
