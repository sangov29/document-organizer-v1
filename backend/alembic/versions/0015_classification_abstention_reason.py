"""add classification abstention reason

Revision ID: 0015
Revises: 0014
"""
from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    # Revision 0001 creates the current SQLAlchemy metadata for a brand-new
    # database.  Such a database can therefore already contain this column by
    # the time Alembic reaches 0015.  Existing installations still need the
    # column added, so make the transition safe for both paths.
    op.execute(
        "ALTER TABLE classification_results "
        "ADD COLUMN IF NOT EXISTS abstention_reason VARCHAR(128)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE classification_results "
        "DROP COLUMN IF EXISTS abstention_reason"
    )
