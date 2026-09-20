from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Document, Page, PreprocessingResult
from app.services.storage import storage
from conftest import extract_token_from_mail, login, wait_for_ingestion, wait_for_mail_text
from fixtures import png_bytes


def test_document_deletion_and_owner_visible_audit(
    api, evidence, auth_token, email_factory, password_factory, run_id
):
    body = png_bytes(run_id, "lifecycle-delete")
    uploaded = api.request(
        "POST", "/documents", label="lifecycle upload", token=auth_token,
        files={"file": ("delete-me.png", body, "image/png")},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["id"]
    evidence.document(document_id)
    wait_for_ingestion(document_id)

    audit = api.request(
        "GET", f"/documents/{document_id}/audit",
        label="lifecycle document audit", token=auth_token,
    )
    assert audit.status_code == 200
    assert audit.json()["schema_version"] == "audit-export-v0.1"
    assert any(event["event_type"] == "upload" for event in audit.json()["events"])

    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        pages = db.scalars(select(Page).where(Page.document_id == document.id)).all()
        page_ids = [page.id for page in pages]
        normalized = db.scalars(
            select(PreprocessingResult.normalized_object_key)
            .where(PreprocessingResult.page_id.in_(page_ids))
        ).all()
        object_keys = [document.object_key, *(page.derived_object_key for page in pages), *normalized]
        assert all(storage.exists(key) for key in object_keys if key)
    finally:
        db.close()

    email_b = email_factory("lifecycle-foreign")
    password_b = password_factory("lifecycle-foreign")
    assert api.request(
        "POST", "/auth/register", label="lifecycle register foreign",
        json={"email": email_b, "password": password_b},
    ).status_code == 202
    verification = extract_token_from_mail(
        wait_for_mail_text(email_b, subject_phrase="Verify"), "/verify-email"
    )
    assert api.request(
        "POST", "/auth/verify-email", label="lifecycle verify foreign",
        json={"token": verification},
    ).status_code == 200
    foreign_login = login(api, email_b, password_b, label="lifecycle login foreign")
    foreign_token = foreign_login.json()["access_token"]
    foreign_audit = api.request(
        "GET", f"/documents/{document_id}/audit",
        label="lifecycle foreign audit denied", token=foreign_token,
    )
    foreign_delete = api.request(
        "DELETE", f"/documents/{document_id}",
        label="lifecycle foreign delete denied", token=foreign_token,
    )
    missing_delete = api.request(
        "DELETE", f"/documents/{uuid.uuid4()}",
        label="lifecycle missing delete", token=foreign_token,
    )
    assert foreign_audit.status_code == 404
    assert foreign_delete.status_code == missing_delete.status_code == 404
    assert foreign_delete.json() == missing_delete.json()

    deleted = api.request(
        "DELETE", f"/documents/{document_id}",
        label="lifecycle owner delete", token=auth_token,
    )
    assert deleted.status_code == 204
    assert api.request(
        "GET", f"/documents/{document_id}",
        label="lifecycle deleted document unavailable", token=auth_token,
    ).status_code == 404
    assert all(not storage.exists(key) for key in object_keys if key)

    account_audit = api.request(
        "GET", "/documents/audit", label="lifecycle deletion audit retained",
        token=auth_token,
    )
    assert account_audit.json()["schema_version"] == "audit-export-v0.1"
    deletion = next(
        event for event in account_audit.json()["events"]
        if event["event_type"] == "deletion" and event["target_id"] == document_id
    )
    assert deletion["metadata"]["action"] == "permanent_delete"
    assert deletion["metadata"]["object_count"] == len(set(key for key in object_keys if key))

    exported_audit = api.request(
        "GET", "/documents/audit/export.json",
        label="lifecycle stable audit export", token=auth_token,
    )
    assert exported_audit.status_code == 200
    assert exported_audit.headers["cache-control"] == "no-store, private"
    assert exported_audit.json()["schema_version"] == "audit-export-v0.1"

    reuploaded = api.request(
        "POST", "/documents", label="lifecycle reupload after deletion", token=auth_token,
        files={"file": ("delete-me-again.png", body, "image/png")},
    )
    assert reuploaded.status_code == 202
    assert reuploaded.json()["id"] != document_id
    evidence.document(reuploaded.json()["id"])
    evidence.note("document-lifecycle", {"deleted": document_id, "reuploaded": reuploaded.json()["id"]})


def test_document_replacement_preserves_version_history(api, evidence, auth_token, run_id):
    original = api.request(
        "POST", "/documents", label="version original", token=auth_token,
        files={"file": ("policy-v1.png", png_bytes(run_id, "version-v1"), "image/png")},
    )
    assert original.status_code == 202
    first = original.json()
    evidence.document(first["id"])
    assert first["version_number"] == 1
    assert first["replaces_document_id"] is None
    wait_for_ingestion(first["id"])

    replacement = api.request(
        "POST", f"/documents/{first['id']}/versions",
        label="version replacement", token=auth_token,
        files={"file": ("policy-v2.png", png_bytes(run_id, "version-v2"), "image/png")},
    )
    assert replacement.status_code == 202
    second = replacement.json()
    evidence.document(second["id"])
    assert second["id"] != first["id"]
    assert second["sha256"] != first["sha256"]
    assert second["replaces_document_id"] == first["id"]
    assert second["version_group_id"] == first["id"]
    assert second["version_number"] == 2
    wait_for_ingestion(second["id"])

    history = api.request(
        "GET", f"/documents/{second['id']}/versions",
        label="version history", token=auth_token,
    )
    assert history.status_code == 200
    assert [(item["id"], item["version_number"]) for item in history.json()] == [
        (second["id"], 2), (first["id"], 1),
    ]
    assert api.request(
        "GET", f"/documents/{first['id']}",
        label="prior version remains available", token=auth_token,
    ).status_code == 200
    evidence.note("document-version-history", history.json())
