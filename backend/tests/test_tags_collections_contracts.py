from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tags_and_collections_are_owner_scoped_and_filterable():
    source = (ROOT / "app" / "api" / "documents.py").read_text()
    assert "Tag.user_id == user.id" in source
    assert "Collection.user_id == user.id" in source
    assert "document_tags.c.document_id == Document.id" in source
    assert "collection_documents.c.document_id == Document.id" in source
    assert '@router.put("/{document_id}/tags/{tag_id}"' in source
    assert '@router.put("/{document_id}/collections/{collection_id}"' in source


def test_tags_and_collections_have_cascade_safe_join_tables():
    migration = (ROOT / "alembic" / "versions" / "0009_tags_collections.py").read_text()
    assert 'down_revision = "0008"' in migration
    assert '"document_tags"' in migration and '"collection_documents"' in migration
    assert migration.count('ondelete="CASCADE"') >= 6
