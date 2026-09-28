"""add classification abstention reason

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "classification_results",
        sa.Column("abstention_reason", sa.String(length=128), nullable=True),
    )


def downgrade():
    op.drop_column("classification_results", "abstention_reason")
