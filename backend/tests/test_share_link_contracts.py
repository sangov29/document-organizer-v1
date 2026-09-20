from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_share_model_persists_digest_not_bearer_token():
    source = (ROOT / "app" / "models" / "entities.py").read_text()
    assert "class ShareLink(Base):" in source
    assert "token_digest: Mapped[str]" in source
    assert "token: Mapped" not in source
    assert 'ForeignKey("documents.id", ondelete="CASCADE")' in source


def test_share_migration_is_sequential_and_fresh_install_safe():
    source = (ROOT / "alembic" / "versions" / "0012_share_links.py").read_text()
    assert 'down_revision = "0011"' in source
    assert 'if "share_links" not in tables' in source
    assert 'op.create_table(' in source
    assert '"ix_share_links_token_digest"' in source


def test_share_routes_are_owner_scoped_expiring_and_revocable():
    source = (ROOT / "app" / "api" / "shares.py").read_text()
    assert '@router.post("/documents/{document_id}/shares"' in source
    assert '@router.delete("/documents/{document_id}/shares/{share_id}"' in source
    assert "ShareLink.user_id == user.id" in source
    assert "ShareLink.expires_at > now" in source
    assert "ShareLink.revoked_at.is_(None)" in source


def test_public_share_is_structured_masked_and_value_free_in_audit():
    source = (ROOT / "app" / "api" / "shares.py").read_text()
    assert '@router.get("/shares/{token}"' in source
    assert "mask_sensitive_value(field.value)" in source
    assert '"action": "share_accessed"' in source
    assert '"token"' not in source.split("metadata_json=", 1)[1]
    assert "storage.get_bytes" not in source


def test_share_ui_describes_privacy_boundary_and_supports_revocation():
    detail = (ROOT.parent / "frontend" / "app" / "documents" / "[id]" / "page.tsx").read_text()
    public = (ROOT.parent / "frontend" / "app" / "share" / "[token]" / "page.tsx").read_text()
    assert "Sensitive values stay masked" in detail
    assert "revokeShare" in detail
    assert "invalid, expired or revoked" in public
