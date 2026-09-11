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
    assert any(event["event_type"] == "upload" for event in audit.json())

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
    deletion = next(
        event for event in account_audit.json()
        if event["event_type"] == "deletion" and event["target_id"] == document_id
    )
    assert deletion["metadata"]["action"] == "permanent_delete"
    assert deletion["metadata"]["object_count"] == len(set(key for key in object_keys if key))

    reuploaded = api.request(
        "POST", "/documents", label="lifecycle reupload after deletion", token=auth_token,
        files={"file": ("delete-me-again.png", body, "image/png")},
    )
    assert reuploaded.status_code == 202
    assert reuploaded.json()["id"] != document_id
    evidence.document(reuploaded.json()["id"])
    evidence.note("document-lifecycle", {"deleted": document_id, "reuploaded": reuploaded.json()["id"]})
