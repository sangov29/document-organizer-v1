"""version predefined extracted fields

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("extracted_fields")}
    if "schema_version" not in columns:
        op.add_column("extracted_fields", sa.Column("schema_version", sa.String(64)))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("extracted_fields")}
    if "schema_version" in columns:
        op.drop_column("extracted_fields", "schema_version")
