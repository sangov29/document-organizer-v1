"""Source-level contracts for Sprint-1 Slice 3.

These pin UM-TC-003, UM-TC-005 and DI-TC-005 invariants without pretending
to replace running-stack acceptance evidence.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1] / "app"
AUTH = ROOT / "api" / "auth.py"
SECURITY = ROOT / "core" / "security.py"
ENTITIES = ROOT / "models" / "entities.py"
SESSION = ROOT / "services" / "session_store.py"
DOCUMENTS = ROOT / "api" / "documents.py"
WORKER = ROOT / "workers" / "celery_app.py"


def _source(path: Path) -> str:
    return path.read_text()


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def test_password_reset_request_has_no_account_existence_branch_and_always_queues_delivery():
    tree = ast.parse(_source(AUTH))
    fn = _function(tree, "request_password_reset")
    assert not any(isinstance(n, ast.If) for n in ast.walk(fn)), (
        "Password-reset request must not branch on account existence"
    )
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert any(
        isinstance(c.func, ast.Attribute)
        and c.func.attr == "delay"
        and isinstance(c.func.value, ast.Name)
        and c.func.value.id == "send_password_reset_email"
        for c in calls
    ), "Every reset request must enqueue the same delivery task"
    assert not any(
        isinstance(c.func, ast.Attribute)
        and isinstance(c.func.value, ast.Name)
        and c.func.value.id == "db"
        for c in calls
    ), "Public reset request must not query account existence in-process"


def test_password_reset_token_is_expiring_versioned_one_time_and_replaces_password():
    security = _source(SECURITY)
    auth = _source(AUTH)
    entities = _source(ENTITIES)
    assert '"password_reset"' in security
    assert 'settings.password_reset_token_minutes' in security
    assert '"rv"' in security
    assert "reset_version: Mapped[int]" in entities
    assert "user.reset_version != reset_version" in auth
    assert "user.reset_version += 1" in auth
    assert "user.password_hash = hash_password(payload.new_password)" in auth


def test_password_reset_revokes_all_existing_server_side_sessions():
    auth = _source(AUTH)
    session = _source(SESSION)
    assert "session_store.revoke_all(str(user.id))" in auth
    assert "def revoke_all(self, user_id: str)" in session
    assert "pipe.delete(self._key(session_id))" in session


def test_totp_secret_is_encrypted_at_rest_and_login_enforces_code_when_enabled():
    security = _source(SECURITY)
    auth = _source(AUTH)
    entities = _source(ENTITIES)
    assert "totp_secret_ciphertext: Mapped[str | None]" in entities
    assert "totp_secret: Mapped" not in entities
    assert "Fernet(settings.totp_fernet_key.encode())" in security
    assert "encrypt_totp_secret(secret)" in auth
    assert "decrypt_totp_secret(user.totp_secret_ciphertext)" in auth
    assert "if user.totp_enabled:" in auth
    assert "verify_totp_code(totp_secret, payload.totp_code)" in auth


def test_totp_is_only_enabled_after_successful_confirmation():
    tree = ast.parse(_source(AUTH))
    setup = _function(tree, "setup_totp")
    confirm = _function(tree, "confirm_totp")
    setup_src = ast.unparse(setup)
    confirm_src = ast.unparse(confirm)
    assert "totp_enabled = True" not in setup_src
    assert "verify_totp_code" in confirm_src
    assert "user.totp_enabled = True" in confirm_src


def test_bulk_upload_processes_each_file_inside_its_own_failure_boundary():
    tree = ast.parse(_source(DOCUMENTS))
    fn = _function(tree, "bulk_upload_documents")
    loops = [n for n in fn.body if isinstance(n, ast.For)]
    assert loops, "Bulk upload must iterate files independently"
    loop = loops[0]
    assert any(isinstance(n, ast.Try) for n in loop.body), (
        "Each bulk file must have its own try/except boundary"
    )
    loop_src = ast.unparse(loop)
    assert "_persist_upload" in loop_src
    assert "outcome='queued'" in loop_src or 'outcome="queued"' in loop_src
    assert "outcome='rejected'" in loop_src or 'outcome="rejected"' in loop_src
    assert "outcome='failed'" in loop_src or 'outcome="failed"' in loop_src


def test_persist_upload_commits_and_enqueues_one_document_at_a_time():
    tree = ast.parse(_source(DOCUMENTS))
    fn = _function(tree, "_persist_upload")
    src = ast.unparse(fn)
    commit_pos = src.find("db.commit()")
    delay_pos = src.find("bootstrap_pipeline.delay")
    assert commit_pos >= 0 and delay_pos > commit_pos, (
        "Each successful document must commit independently before queue handoff"
    )


def test_document_by_id_is_scoped_to_authenticated_owner():
    source = _source(DOCUMENTS)
    assert 'Document.id == document_id' in source
    assert 'Document.user_id == user.id' in source
    assert 'status_code=404, detail="Document not found"' in source


def test_duplicate_keep_is_explicit_linked_and_audited():
    source = _source(DOCUMENTS)
    entities = _source(ENTITIES)
    assert 'Literal["reject", "keep"]' in source
    assert 'duplicate_of_document_id=(existing.id if existing else None)' in source
    assert 'AuditEventType.DUPLICATE_OVERRIDE' in source
    assert 'duplicate_of_document_id: Mapped[uuid.UUID | None]' in entities
    assert 'postgresql_where=text("duplicate_of_document_id IS NULL")' in entities


def test_password_reset_delivery_worker_noops_for_unknown_accounts_but_tokenizes_real_accounts():
    worker = _source(WORKER)
    assert "def send_password_reset_email(email: str)" in worker
    assert 'if not user or not user.is_verified:' in worker
    assert 'return {"status": "noop"}' in worker
    assert "create_password_reset_token(str(user.id), user.reset_version)" in worker
