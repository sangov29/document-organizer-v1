"""email verification token invalidation state

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "verification_version" not in columns:
        op.add_column("users", sa.Column("verification_version", sa.Integer(), nullable=False, server_default="0"))
        op.alter_column("users", "verification_version", server_default=None)


def downgrade():
    op.drop_column("users", "verification_version")
