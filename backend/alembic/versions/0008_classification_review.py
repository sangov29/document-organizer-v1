"""persistent classification review state

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("classification_results")}
    if "reviewed_at" not in columns:
        op.add_column("classification_results", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("classification_results")}
    if "reviewed_at" in columns:
        op.drop_column("classification_results", "reviewed_at")
