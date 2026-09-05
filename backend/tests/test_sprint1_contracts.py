"""Source-level contracts for the second Sprint-1 slice.

These do not replace UM/DI acceptance execution against a running stack. They
pin the architectural/security invariants so a later refactor cannot silently
turn one-time verification into reusable tokens, fake logout, or remove PDF
page persistence.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1] / "app"
AUTH = ROOT / "api" / "auth.py"
DEPS = ROOT / "api" / "deps.py"
SECURITY = ROOT / "core" / "security.py"
WORKER = ROOT / "workers" / "celery_app.py"
ENTITIES = ROOT / "models" / "entities.py"


def _source(path: Path) -> str:
    return path.read_text()


def test_verification_token_is_expiring_and_versioned_for_one_time_use():
    security = _source(SECURITY)
    auth = _source(AUTH)
    entities = _source(ENTITIES)
    assert 'create_email_verification_token' in security
    assert '"email_verification"' in security
    assert 'settings.verification_token_minutes' in security
    assert '"vv"' in security
    assert '"exp":' in security
    assert '"type": token_type' in security
    assert "verification_version: Mapped[int]" in entities
    assert "user.verification_version += 1" in auth
    assert "user.verification_version != verification_version" in auth


def test_logout_revokes_server_side_session_and_auth_dependency_touches_ttl():
    auth = _source(AUTH)
    deps = _source(DEPS)
    security = _source(SECURITY)
    assert "session_store.revoke(context.session_id)" in auth
    assert "session_store.touch(session_id, str(user.id))" in deps
    assert '"sid": session_id' in security


def test_registration_queues_verification_delivery_after_both_account_paths():
    tree = ast.parse(_source(AUTH))
    register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "register")

    # The verification-delivery call must be a top-level statement in register,
    # after the new-vs-existing account branch. Merely finding a .delay() call
    # somewhere below register is insufficient: putting it inside only one side
    # of the branch would reintroduce an account-enumeration signal.
    account_branch_index = next(
        i for i, node in enumerate(register.body)
        if isinstance(node, ast.If)
    )

    top_level_delay_indexes = []
    for i, node in enumerate(register.body):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "delay":
            top_level_delay_indexes.append(i)

    assert top_level_delay_indexes, (
        "Registration must enqueue verification delivery as a top-level statement, "
        "not inside only one account-existence branch"
    )
    assert all(i > account_branch_index for i in top_level_delay_indexes), (
        "Verification delivery must occur after the full new-vs-existing account branch"
    )

    branch = register.body[account_branch_index]
    nested_delay_calls = [
        n for n in ast.walk(branch)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "delay"
    ]
    assert not nested_delay_calls, (
        "Verification delivery must not be nested inside either registration branch"
    )


def test_pdf_splitter_persists_page_rows_and_single_page_pdf_objects():
    worker = _source(WORKER)
    assert "PdfReader" in worker and "PdfWriter" in worker
    assert "db.add(Page(document_id=document.id, page_number=index" in worker
    assert 'pages/{page_number}.pdf' in worker
    assert "return len(reader.pages)" in worker
