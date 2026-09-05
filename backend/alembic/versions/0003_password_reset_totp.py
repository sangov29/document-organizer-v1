"""password reset version and encrypted TOTP secret

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "reset_version" not in columns:
        op.add_column("users", sa.Column("reset_version", sa.Integer(), nullable=False, server_default="0"))
        op.alter_column("users", "reset_version", server_default=None)
    if "totp_secret_ciphertext" not in columns:
        op.add_column("users", sa.Column("totp_secret_ciphertext", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("users", "totp_secret_ciphertext")
    op.drop_column("users", "reset_version")
