"""document replacement version lineage

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("documents")}
    if "replaces_document_id" not in columns:
        op.add_column("documents", sa.Column("replaces_document_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            "fk_documents_replaces_document_id", "documents", "documents",
            ["replaces_document_id"], ["id"], ondelete="SET NULL",
        )
        op.create_index("ix_documents_replaces_document_id", "documents", ["replaces_document_id"])
    if "version_group_id" not in columns:
        op.add_column("documents", sa.Column("version_group_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index("ix_documents_version_group_id", "documents", ["version_group_id"])
    if "version_number" not in columns:
        op.add_column("documents", sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"))
        op.create_check_constraint("ck_document_version_number", "documents", "version_number >= 1")


def downgrade():
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("documents")}
    if "version_number" in columns:
        op.drop_constraint("ck_document_version_number", "documents", type_="check")
        op.drop_column("documents", "version_number")
    if "version_group_id" in columns:
        op.drop_index("ix_documents_version_group_id", table_name="documents")
        op.drop_column("documents", "version_group_id")
    if "replaces_document_id" in columns:
        op.drop_index("ix_documents_replaces_document_id", table_name="documents")
        op.drop_constraint("fk_documents_replaces_document_id", "documents", type_="foreignkey")
        op.drop_column("documents", "replaces_document_id")
