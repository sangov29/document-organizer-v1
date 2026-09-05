"""traceable page preprocessing results

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    # Revision 0001 uses current Base.metadata for a fresh database, so a new
    # installation may already contain this table. Existing databases stamped
    # at 0004 do not. Keep the additive migration safe for both paths.
    if "preprocessing_results" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "preprocessing_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("normalized_object_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("orientation_degrees", sa.Integer()),
        sa.Column("orientation_confidence", sa.Float()),
        sa.Column("skew_degrees", sa.Float()),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.Column("quality_metadata", sa.JSON(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("noise_reduction_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_preprocessing_results_page_id", "preprocessing_results", ["page_id"], unique=True)


def downgrade():
    if "preprocessing_results" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_preprocessing_results_page_id", table_name="preprocessing_results")
        op.drop_table("preprocessing_results")
