from pathlib import Path

from app.services.integrity_conflicts import upload_conflict_detail


ROOT = Path(__file__).resolve().parents[1]


def test_document_version_model_preserves_direct_and_group_lineage():
    source = (ROOT / "app" / "models" / "entities.py").read_text()
    assert "replaces_document_id: Mapped[uuid.UUID | None]" in source
    assert "version_group_id: Mapped[uuid.UUID | None]" in source
    assert "version_number: Mapped[int]" in source
    assert 'CheckConstraint("version_number >= 1"' in source


def test_document_version_migration_is_sequential_and_fresh_install_safe():
    source = (ROOT / "alembic" / "versions" / "0011_document_versions.py").read_text()
    assert 'down_revision = "0010"' in source
    assert 'get_columns("documents")' in source
    assert 'if "replaces_document_id" not in columns' in source
    assert 'if "version_group_id" not in columns' in source
    assert 'if "version_number" not in columns' in source


def test_version_routes_are_owner_scoped_and_inherit_organization():
    source = (ROOT / "app" / "api" / "documents.py").read_text()
    assert '@router.post("/{document_id}/versions"' in source
    assert '@router.get("/{document_id}/versions"' in source
    assert "previous = _owned_document(db, user, document_id)" in source
    assert "inherited_tags=list(previous.tags)" in source
    assert "inherited_collections=list(previous.collections)" in source


def test_version_history_is_ordered_and_owner_filtered():
    source = (ROOT / "app" / "api" / "documents.py").read_text()
    assert "Document.user_id == user.id" in source
    assert "Document.version_group_id == group_id" in source
    assert "Document.version_number.desc()" in source


def test_default_library_queries_only_expose_current_versions():
    source = (ROOT / "app" / "api" / "documents.py").read_text()
    assert "def _current_document_clause():" in source
    assert "newer.version_number > Document.version_number" in source
    assert source.count("_current_document_clause()") >= 4
    assert "include_versions: bool = False" in source


def test_version_number_uniqueness_is_enforced_at_the_database():
    source = (ROOT / "app" / "models" / "entities.py").read_text()
    assert '"uq_document_version_group_number"' in source
    assert 'text("COALESCE(version_group_id, id)")' in source
    assert '"version_number"' in source
    assert "unique=True" in source


def test_version_uniqueness_migration_renumbers_duplicates_before_indexing():
    source = (ROOT / "alembic" / "versions" / "0013_version_group_uniqueness.py").read_text()
    assert 'down_revision = "0012"' in source
    assert "INDEX_NAME in indexes" in source  # fresh-install safe: skip if already present
    assert "ROW_NUMBER() OVER" in source
    assert "PARTITION BY COALESCE(version_group_id, id)" in source
    assert "ORDER BY version_number, uploaded_at, id" in source
    assert "CREATE UNIQUE INDEX uq_document_version_group_number" in source
    assert "((COALESCE(version_group_id, id)), version_number)" in source


def test_migration_includes_root_and_preserves_valid_version_order():
    """The migration grouping must rank root 1 with children 2 and 3."""
    source = (ROOT / "alembic" / "versions" / "0013_version_group_uniqueness.py").read_text()
    assert "WHERE version_group_id IS NOT NULL" not in source
    assert source.count("COALESCE(version_group_id, id)") >= 2
    assert "documents.version_number IS DISTINCT FROM ranked.rn" in source


def test_concurrent_version_conflict_is_a_stable_409_not_an_unhandled_500():
    source = (ROOT / "app" / "api" / "documents.py").read_text()
    assert "except IntegrityError as exc:" in source
    assert "detail=upload_conflict_detail(exc)" in source

    class Diagnostic:
        constraint_name = "uq_document_version_group_number"

    class DriverError:
        diag = Diagnostic()

    class FakeIntegrityError(Exception):
        orig = DriverError()

    detail = upload_conflict_detail(FakeIntegrityError())
    assert detail["code"] == "version_conflict"
    assert "retry" in detail["message"].lower()

    fallback = upload_conflict_detail(Exception())
    assert fallback == {"code": "duplicate_document"}
