from __future__ import annotations

import json
import threading
import time
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Document, Page, PreprocessingResult
from app.services.storage import storage
from conftest import extract_token_from_mail, login, wait_for_ingestion, wait_for_mail_text
from fixtures import document_png, png_bytes


def _wait_for_analysis(api, auth_token, document_id, label, timeout=120.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = api.request(
            "GET", f"/documents/{document_id}/analysis",
            label=label, token=auth_token,
        )
        if latest.status_code == 200:
            return latest.json()
        assert latest.status_code in {202, 404}, latest.text
        time.sleep(0.5)
    raise AssertionError(
        f"Document {document_id} analysis did not become ready; "
        f"last response={latest.status_code if latest else 'none'}"
    )


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

    current_library = api.request(
        "GET", "/documents", label="current-version library", token=auth_token,
    )
    assert current_library.status_code == 200
    current_ids = {item["id"] for item in current_library.json()}
    assert second["id"] in current_ids
    assert first["id"] not in current_ids

    complete_library = api.request(
        "GET", "/documents?include_versions=true",
        label="complete version library", token=auth_token,
    )
    complete_ids = {item["id"] for item in complete_library.json()}
    assert {first["id"], second["id"]} <= complete_ids

    current_search = api.request(
        "GET", "/documents/search?page_size=100",
        label="current-version search", token=auth_token,
    )
    assert current_search.status_code == 200
    search_ids = {item["id"] for item in current_search.json()["items"]}
    assert second["id"] in search_ids
    assert first["id"] not in search_ids

    complete_search = api.request(
        "GET", "/documents/search?page_size=100&include_versions=true",
        label="complete version search", token=auth_token,
    )
    complete_search_ids = {item["id"] for item in complete_search.json()["items"]}
    assert {first["id"], second["id"]} <= complete_search_ids
    evidence.note("document-version-history", history.json())


def test_time_limited_share_is_masked_revocable_and_non_enumerating(api, evidence, auth_token, run_id):
    uploaded = api.request(
        "POST", "/documents", label="share banking upload", token=auth_token,
        files={"file": ("shared-bank.png", document_png(run_id, "share-bank", lines=[
            "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
            "Bank Name: Example Community Bank", "Account Holder: Share Test",
            "Account Number: 555566667777", "Statement Date: 05 September 2026",
        ]), "image/png")},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["id"]
    evidence.document(document_id)
    wait_for_ingestion(document_id)

    # A share is a structured projection, so creation begins only after the
    # classification/field analysis contract is ready (not merely ingestion).
    _wait_for_analysis(api, auth_token, document_id, "wait for share analysis")

    created = api.request(
        "POST", f"/documents/{document_id}/shares",
        label="create time-limited share", token=auth_token,
        json={"expires_in_hours": 24},
    )
    assert created.status_code == 201
    share = created.json()
    assert share["id"] and share["token"] and share["expires_at"]

    listed = api.request(
        "GET", f"/documents/{document_id}/shares",
        label="list persisted owner share", token=auth_token,
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == share["id"]
    assert share["token"] not in json.dumps(listed.json())

    public = api.request(
        "GET", f"/shares/{share['token']}", label="read masked public share",
    )
    assert public.status_code == 200
    assert public.headers["cache-control"] == "no-store"
    public_text = json.dumps(public.json())
    assert public.json()["family"] == "banking"
    assert "555566667777" not in public_text
    account = {item["field_name"]: item for item in public.json()["fields"]}["account_number"]
    assert account["sensitive"] is True and account["masked"] is True
    assert account["value"] != "555566667777"

    tampered_token = share["token"][:-1] + ("A" if share["token"][-1] != "A" else "B")
    assert api.request(
        "GET", f"/shares/{tampered_token}", label="tampered share denied",
    ).status_code == 404

    revoked = api.request(
        "DELETE", f"/documents/{document_id}/shares/{share['id']}",
        label="revoke share", token=auth_token,
    )
    assert revoked.status_code == 204
    revoked_read = api.request(
        "GET", f"/shares/{share['token']}", label="revoked share denied",
    )
    missing_read = api.request(
        "GET", f"/shares/{uuid.uuid4().hex}", label="missing share denied",
    )
    assert revoked_read.status_code == missing_read.status_code == 404
    assert revoked_read.json() == missing_read.json()

    audit = api.request(
        "GET", f"/documents/{document_id}/audit",
        label="share lifecycle audit", token=auth_token,
    )
    audit_text = json.dumps(audit.json())
    actions = {event["metadata"].get("action") for event in audit.json()["events"]}
    assert {"share_created", "share_accessed", "share_revoked"} <= actions
    assert share["token"] not in audit_text
    assert "555566667777" not in audit_text
    evidence.note("share-link-lifecycle", {"document_id": document_id, "share_id": share["id"]})


def test_share_view_is_rate_limited_per_token_with_window_recovery_and_isolation(
    api, evidence, auth_token, run_id
):
    def _create_share(marker):
        uploaded = api.request(
            "POST", "/documents", label=f"share-throttle upload {marker}", token=auth_token,
            files={"file": (f"throttle-{marker}.png", document_png(
                run_id, f"share-throttle-{marker}",
                lines=["UTILITY BILL", "ELECTRICITY SERVICE", f"Provider: Throttle {marker}"],
            ), "image/png")},
        )
        assert uploaded.status_code == 202
        document_id = uploaded.json()["id"]
        evidence.document(document_id)
        wait_for_ingestion(document_id)
        _wait_for_analysis(
            api, auth_token, document_id,
            f"wait for share-throttle analysis {marker}",
        )
        created = api.request(
            "POST", f"/documents/{document_id}/shares",
            label=f"create share {marker}", token=auth_token,
            json={"expires_in_hours": 24},
        )
        assert created.status_code == 201
        return created.json()["token"]

    token_a = _create_share("a")
    token_b = _create_share("b")

    # Valid access + threshold enforcement. The acceptance environment pins
    # SHARE_VIEW_RATE_LIMIT=3 / SHARE_VIEW_RATE_WINDOW_SECONDS=2 (see
    # docker-compose.acceptance.yml) specifically so this is exercised in
    # seconds against the real limiter rather than needing the V1 default
    # (30/60s) or a mocked clock.
    for attempt in range(3):
        ok = api.request("GET", f"/shares/{token_a}", label=f"share view under threshold #{attempt + 1}")
        assert ok.status_code == 200

    throttled = api.request("GET", f"/shares/{token_a}", label="share view over threshold")
    assert throttled.status_code == 429
    assert "Retry-After" in throttled.headers
    assert int(throttled.headers["Retry-After"]) > 0

    # Isolation between links: a separate share link has its own independent
    # budget and is unaffected by link A's limit being exhausted.
    isolated = api.request("GET", f"/shares/{token_b}", label="different share link unaffected")
    assert isolated.status_code == 200

    # Window recovery: once the (short, test-only) window elapses, the same
    # link is viewable again without needing a new share to be created.
    time.sleep(2.5)
    recovered = api.request("GET", f"/shares/{token_a}", label="share view after window recovery")
    assert recovered.status_code == 200

    # Malformed tokens have the same budget shape because limiting happens
    # before parsing. Once the fixed window expires they return to the normal
    # non-enumerating 404—not 200—and a rejected request must not refresh the
    # TTL into an indefinitely sliding window.
    malformed = "not-a-valid-share-token"
    for attempt in range(3):
        missing = api.request(
            "GET", f"/shares/{malformed}", label=f"malformed share under threshold #{attempt + 1}",
        )
        assert missing.status_code == 404
    malformed_throttled = api.request("GET", f"/shares/{malformed}", label="malformed share throttled")
    assert malformed_throttled.status_code == 429
    time.sleep(1.0)
    still_throttled = api.request("GET", f"/shares/{malformed}", label="malformed share remains throttled")
    assert still_throttled.status_code == 429
    time.sleep(1.5)
    malformed_recovered = api.request("GET", f"/shares/{malformed}", label="malformed share after recovery")
    assert malformed_recovered.status_code == 404

    evidence.note("share-view-throttling", {
        "threshold_enforced": True,
        "isolation_confirmed": True,
        "window_recovery_confirmed": True,
        "malformed_token_recovered_to_404": True,
        "rejected_request_did_not_extend_window": True,
    })


def test_concurrent_version_uploads_cannot_create_duplicate_version_numbers(
    api, evidence, auth_token, run_id
):
    original = api.request(
        "POST", "/documents", label="version-race original", token=auth_token,
        files={"file": ("race-v1.png", png_bytes(run_id, "version-race"), "image/png")},
    )
    assert original.status_code == 202
    document_id = original.json()["id"]
    evidence.document(document_id)
    wait_for_ingestion(document_id)

    results: list = [None, None]

    def _upload_version(index):
        results[index] = api.request(
            "POST", f"/documents/{document_id}/versions",
            label=f"concurrent version upload {index}", token=auth_token,
            files={"file": (f"race-v{index}.png", png_bytes(run_id, f"version-race-{index}"), "image/png")},
        )

    threads = [threading.Thread(target=_upload_version, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Whether the two requests actually raced at the DB level is timing-
    # dependent and not something this test can force deterministically.
    # What must always hold, race or no race, is the safety invariant the
    # uq_document_version_group_number constraint exists to guarantee: no
    # two documents in the same version group ever end up with the same
    # version_number. A legitimate conflict must surface as 409, never 500.
    statuses = {response.status_code for response in results}
    assert statuses <= {202, 409}, f"unexpected status codes from concurrent uploads: {statuses}"
    assert 202 in statuses, "at least one concurrent version upload must succeed"

    for response in results:
        if response.status_code == 202:
            evidence.document(response.json()["id"])

    history = api.request(
        "GET", f"/documents/{document_id}/versions",
        label="version history after concurrent uploads", token=auth_token,
    )
    assert history.status_code == 200
    numbers = [item["version_number"] for item in history.json()]
    assert len(numbers) == len(set(numbers)), (
        f"duplicate version_number values were created under concurrency: {numbers}"
    )

    evidence.note("concurrent-version-uploads", {
        "statuses": sorted(statuses), "version_numbers": sorted(numbers),
    })
