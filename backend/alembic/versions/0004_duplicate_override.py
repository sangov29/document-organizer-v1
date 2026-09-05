"""allow explicitly retained duplicate documents

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if "duplicate_of_document_id" not in columns:
        op.add_column(
            "documents",
            sa.Column("duplicate_of_document_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            "fk_documents_duplicate_of_document_id",
            "documents", "documents",
            ["duplicate_of_document_id"], ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_documents_duplicate_of_document_id",
            "documents", ["duplicate_of_document_id"], unique=False,
        )

    inspector = sa.inspect(bind)
    unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("documents")
    }
    if "uq_document_user_hash" in unique_constraints:
        op.drop_constraint("uq_document_user_hash", "documents", type_="unique")

    indexes = {index["name"] for index in inspector.get_indexes("documents")}
    if "uq_document_user_hash_canonical" not in indexes:
        op.create_index(
            "uq_document_user_hash_canonical",
            "documents", ["user_id", "sha256"], unique=True,
            postgresql_where=sa.text("duplicate_of_document_id IS NULL"),
        )


def downgrade():
    op.drop_index("uq_document_user_hash_canonical", table_name="documents")
    op.create_unique_constraint("uq_document_user_hash", "documents", ["user_id", "sha256"])
    op.drop_index("ix_documents_duplicate_of_document_id", table_name="documents")
    op.drop_constraint("fk_documents_duplicate_of_document_id", "documents", type_="foreignkey")
    op.drop_column("documents", "duplicate_of_document_id")
