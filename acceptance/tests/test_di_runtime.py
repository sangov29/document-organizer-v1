from __future__ import annotations

import hashlib
import os
import time

import pytest

from conftest import wait_for_ingestion
from fixtures import (
    exact_size_pdf,
    jpeg_bytes,
    malformed_pdf_bytes,
    pdf_bytes,
    png_bytes,
    unsupported_bytes,
)

MAX_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "1048576"))


def _upload(api, token, label, filename, content, mime):
    return api.request(
        "POST", "/documents", label=label, token=token,
        files={"file": (filename, content, mime)},
    )


@pytest.mark.catalogue("DI-TC-001", steps="1-7 API-scope")
def test_DI_TC_001_supported_uploads_and_safe_failures(api, evidence, auth_token, run_id):
    fixtures = [
        ("valid.pdf", pdf_bytes(run_id, "di001-pdf"), "application/pdf"),
        ("valid.jpg", jpeg_bytes(run_id, "di001-jpg"), "image/jpeg"),
        ("valid.png", png_bytes(run_id, "di001-png"), "image/png"),
    ]
    for filename, body, mime in fixtures:
        response = _upload(api, auth_token, f"DI-TC-001 upload {filename}", filename, body, mime)
        assert response.status_code == 202
        assert response.json()["status"] == "QUEUED"
        evidence.document(response.json()["id"])

    unsupported = _upload(
        api, auth_token, "DI-TC-001 unsupported", "unsupported.txt",
        unsupported_bytes(run_id, "di001-unsupported"), "text/plain",
    )
    assert unsupported.status_code == 415
    assert "PDF" in str(unsupported.json()) and "PNG" in str(unsupported.json())

    malformed = _upload(
        api, auth_token, "DI-TC-001 malformed PDF", "malformed.pdf",
        malformed_pdf_bytes(run_id, "di001-malformed"), "application/pdf",
    )
    assert malformed.status_code == 202
    malformed_id = malformed.json()["id"]
    evidence.document(malformed_id)
    failed = wait_for_ingestion(malformed_id, expected_job_status="FAILED")
    evidence.note("malformed-pdf-worker", failed)
    assert failed["error_code"]

    unusual_name = '<img src=x onerror=alert(1)> & acceptance.png'
    unusual = _upload(
        api, auth_token, "DI-TC-001 unusual filename", unusual_name,
        png_bytes(run_id, "di001-name"), "image/png",
    )
    assert unusual.status_code == 202
    assert unusual.json()["original_filename"] == unusual_name
    # API evidence can prove it remains data, not browser execution. Literal UI
    # screenshot evidence remains outside this API-only harness by design.
    evidence.note("filename-api-safety", {"round_trip_literal": True, "ui_execution_not_claimed": True})


@pytest.mark.catalogue("DI-TC-002", steps="1-4,6")
def test_DI_TC_002_exact_duplicate_core(api, evidence, auth_token, run_id):
    original = pdf_bytes(run_id, "di002-original")
    digest = hashlib.sha256(original).hexdigest()
    first = _upload(api, auth_token, "DI-TC-002 initial upload", "A.pdf", original, "application/pdf")
    assert first.status_code == 202
    assert first.json()["sha256"] == digest
    first_id = first.json()["id"]
    evidence.document(first_id)

    before_list = api.request("GET", "/documents", label="DI-TC-002 count before duplicate", token=auth_token)
    before_count = len(before_list.json())
    duplicate = _upload(api, auth_token, "DI-TC-002 identical duplicate", "A-copy.pdf", original, "application/pdf")
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_document"
    after_list = api.request("GET", "/documents", label="DI-TC-002 count after duplicate", token=auth_token)
    assert len(after_list.json()) == before_count
    evidence.note("hash-evidence", {"fixture_sha256": digest, "stored_sha256": first.json()["sha256"], "same": True})

    similar = original + b"\n% byte-different acceptance variant\n"
    different = _upload(api, auth_token, "DI-TC-002 byte-different", "A-visual-variant.pdf", similar, "application/pdf")
    assert different.status_code == 202
    assert different.json()["sha256"] != digest


@pytest.mark.catalogue("DI-TC-002", steps="5")
@pytest.mark.known_gap
@pytest.mark.xfail(strict=True, reason="No public duplicate proceed/keep override exists yet; harness will not invent semantics")
def test_DI_TC_002_keep_override_known_gap():
    pytest.fail("DI-TC-002 step 5 requires a public proceed/keep duplicate action")


@pytest.mark.catalogue("DI-TC-003", steps="1-6")
def test_DI_TC_003_capacity_limit(api, evidence, auth_token, run_id):
    below = exact_size_pdf(run_id, "di003-below", MAX_BYTES - 1)
    boundary = exact_size_pdf(run_id, "di003-boundary", MAX_BYTES)
    above = exact_size_pdf(run_id, "di003-above", MAX_BYTES + 1)

    r_below = _upload(api, auth_token, "DI-TC-003 below limit", "below.pdf", below, "application/pdf")
    r_boundary = _upload(api, auth_token, "DI-TC-003 boundary", "boundary.pdf", boundary, "application/pdf")
    r_above = _upload(api, auth_token, "DI-TC-003 above limit", "above.pdf", above, "application/pdf")
    assert r_below.status_code == 202
    assert r_boundary.status_code == 202
    assert r_above.status_code == 413
    assert "limit" in str(r_above.json()).lower()

    for index in range(5):
        repeated = _upload(api, auth_token, f"DI-TC-003 repeat oversized {index}", f"too-big-{index}.pdf", above, "application/pdf")
        assert repeated.status_code == 413
    health = api.client.get("http://localhost:8000/health")
    evidence.response("DI-TC-003 health after oversized", health)
    assert health.status_code == 200 and health.json()["status"] == "ok"
    evidence.note("configured-limit", {"acceptance_max_upload_bytes": MAX_BYTES, "source_change_required": False, "docker_stats": "captured by run-local.sh"})


@pytest.mark.catalogue("DI-TC-004", steps="1-5")
def test_DI_TC_004_pdf_page_splitting(api, evidence, auth_token, run_id):
    one = _upload(api, auth_token, "DI-TC-004 one-page", "one-page.pdf", pdf_bytes(run_id, "di004-one", 1), "application/pdf")
    three = _upload(api, auth_token, "DI-TC-004 three-page", "three-page.pdf", pdf_bytes(run_id, "di004-three", 3), "application/pdf")
    assert one.status_code == three.status_code == 202
    one_id, three_id = one.json()["id"], three.json()["id"]
    evidence.document(one_id); evidence.document(three_id)

    one_state = wait_for_ingestion(one_id)
    three_state = wait_for_ingestion(three_id)
    evidence.note("one-page-db-evidence", one_state)
    evidence.note("three-page-db-evidence", three_state)
    assert [p["page_number"] for p in one_state["pages"]] == [1]
    assert [p["page_number"] for p in three_state["pages"]] == [1, 2, 3]
    assert all(p["document_id"] == three_id for p in three_state["pages"])
    assert len({p["derived_object_key"] for p in three_state["pages"]}) == 3


@pytest.mark.catalogue("DI-TC-005", steps="1-6")
def test_DI_TC_005_bulk_partial_failure_isolation(api, evidence, auth_token, run_id):
    files = [
        ("A.pdf", pdf_bytes(run_id, "di005-a"), "application/pdf"),
        ("B.jpg", jpeg_bytes(run_id, "di005-b"), "image/jpeg"),
        ("C.txt", unsupported_bytes(run_id, "di005-c"), "text/plain"),
        ("D.png", png_bytes(run_id, "di005-d"), "image/png"),
    ]
    multipart = [("files", (name, content, mime)) for name, content, mime in files]
    response = api.request("POST", "/documents/bulk", label="DI-TC-005 mixed bulk", token=auth_token, files=multipart)
    assert response.status_code == 200
    payload = response.json()
    outcomes = {item["filename"]: item for item in payload["items"]}
    assert outcomes["C.txt"]["outcome"] == "rejected"
    for name in ("A.pdf", "B.jpg", "D.png"):
        assert outcomes[name]["outcome"] == "queued"
        evidence.document(outcomes[name]["document"]["id"])
    assert payload["queued_count"] == 3
    assert payload["failed_count"] == 1

    # The failed item did not roll back successful siblings. Wait for each valid
    # sibling's independent ingestion job instead of relying on one batch state.
    states = {}
    for name in ("A.pdf", "B.jpg", "D.png"):
        doc_id = outcomes[name]["document"]["id"]
        states[name] = wait_for_ingestion(doc_id)
        assert states[name]["job_status"] == "READY"
    evidence.note("bulk-independent-worker-states", states)

    listing = api.request("GET", "/documents", label="DI-TC-005 final documents", token=auth_token)
    ids = {row["id"] for row in listing.json()}
    assert all(outcomes[name]["document"]["id"] in ids for name in ("A.pdf", "B.jpg", "D.png"))
    assert "C.txt" not in {row["original_filename"] for row in listing.json()}
