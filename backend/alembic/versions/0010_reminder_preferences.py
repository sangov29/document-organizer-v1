"""owner reminder preferences

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("users")}
    if "reminders_enabled" not in columns:
        op.add_column(
            "users",
            sa.Column("reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "reminder_window_days" not in columns:
        op.add_column(
            "users",
            sa.Column("reminder_window_days", sa.Integer(), nullable=False, server_default="90"),
        )


def downgrade():
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("users")}
    if "reminder_window_days" in columns:
        op.drop_column("users", "reminder_window_days")
    if "reminders_enabled" in columns:
        op.drop_column("users", "reminders_enabled")
