"""add corpus document families

Revision ID: 0014
Revises: 0013
"""
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


NEW_FAMILIES = ("HOTEL", "LEGAL_NOTICE", "SHIPPING")


def upgrade():
    for family in NEW_FAMILIES:
        op.execute(f"ALTER TYPE document_family ADD VALUE IF NOT EXISTS '{family}'")


def downgrade():
    # PostgreSQL cannot safely remove enum values while rows may reference
    # them.  A downgrade therefore preserves the expanded enum catalogue.
    pass
