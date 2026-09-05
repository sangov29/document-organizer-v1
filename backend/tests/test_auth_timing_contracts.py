"""Dependency-free regression contracts for auth anti-enumeration password work.

These tests intentionally inspect source rather than importing the FastAPI auth
module, so they can run in minimal CI/static environments before third-party
runtime dependencies are installed. They prevent the two specific regressions
identified during scaffold review. Acceptance-level timing measurement still
belongs to UM-TC-001/UM-TC-002 against a running stack.
"""

import ast
from pathlib import Path


AUTH_PATH = Path(__file__).parents[1] / "app" / "api" / "auth.py"
SECURITY_PATH = Path(__file__).parents[1] / "app" / "core" / "security.py"


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name!r} not found")


def test_registration_existing_branch_performs_hash_work():
    source = AUTH_PATH.read_text()
    register = _function_node(source, "register")

    # The register function must contain an explicit else branch for the
    # existing-account path and that branch must call hash_password.
    if_nodes = [node for node in ast.walk(register) if isinstance(node, ast.If)]
    matching = []
    for node in if_nodes:
        if not node.orelse:
            continue
        calls = [
            call.func.id
            for child in node.orelse
            for call in ast.walk(child)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        ]
        if "hash_password" in calls:
            matching.append(node)

    assert matching, "Existing-email registration path must still execute hash_password()"


def test_registration_applies_common_response_equalization():
    source = AUTH_PATH.read_text()
    register = _function_node(source, "register")
    calls = [
        node.func.id
        for node in ast.walk(register)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert "equalize_registration_response" in calls


def test_unknown_login_uses_dummy_hash_instead_of_short_circuiting_verify():
    source = AUTH_PATH.read_text()
    login = _function_node(source, "login")

    # Guard against the original vulnerable pattern:
    # bool(user and verify_password(...))
    for node in ast.walk(login):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            assert not any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "verify_password"
                for call in ast.walk(node)
            ), "verify_password() must not be short-circuited behind `user and ...`"

    names = {node.id for node in ast.walk(login) if isinstance(node, ast.Name)}
    calls = [
        node
        for node in ast.walk(login)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verify_password"
    ]
    assert "DUMMY_PASSWORD_HASH" in names
    assert calls, "Login must execute verify_password() for both known and unknown emails"


def test_dummy_password_hash_is_process_level_not_per_request():
    source = SECURITY_PATH.read_text()
    tree = ast.parse(source)

    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "DUMMY_PASSWORD_HASH" for target in node.targets)
    ]
    assert assignments, "DUMMY_PASSWORD_HASH must be defined once at module/process level"
