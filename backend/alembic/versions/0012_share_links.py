"""revocable time-limited document share links

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "share_links" not in tables:
        op.create_table(
            "share_links",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_share_links_document_id", "share_links", ["document_id"])
        op.create_index("ix_share_links_user_id", "share_links", ["user_id"])
        op.create_index("ix_share_links_token_digest", "share_links", ["token_digest"], unique=True)
        op.create_index("ix_share_links_expires_at", "share_links", ["expires_at"])


def downgrade():
    if "share_links" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("share_links")
