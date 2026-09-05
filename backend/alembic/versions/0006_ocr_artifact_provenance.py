"""page OCR confidence and provenance metadata

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("ocr_artifacts")}
    additions = {
        "confidence": sa.Column("confidence", sa.Float()),
        "blocks": sa.Column("blocks", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        "method": sa.Column("method", sa.String(128), nullable=False, server_default="printed_text_ocr"),
        "language": sa.Column("language", sa.String(32), nullable=False, server_default="eng"),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("ocr_artifacts", column)
    indexes = inspector.get_indexes("ocr_artifacts")
    has_unique_page_index = any(
        index.get("unique") and index.get("column_names") == ["page_id"]
        for index in indexes
    )
    if not has_unique_page_index:
        op.create_index("uq_ocr_artifacts_page_id", "ocr_artifacts", ["page_id"], unique=True)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("ocr_artifacts")}
    if "uq_ocr_artifacts_page_id" in indexes:
        op.drop_index("uq_ocr_artifacts_page_id", table_name="ocr_artifacts")
    columns = {column["name"] for column in inspector.get_columns("ocr_artifacts")}
    for name in ("language", "method", "blocks", "confidence"):
        if name in columns:
            op.drop_column("ocr_artifacts", name)
