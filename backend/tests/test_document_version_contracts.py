from pathlib import Path


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
