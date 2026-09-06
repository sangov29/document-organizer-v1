from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditEvent, ClassificationResult
from app.models.enums import AuditEventType
from test_cl_ex_runtime import _upload_and_wait


def _known_utility(api, token, run_id, label):
    return _upload_and_wait(api, token, run_id, label, [
        "UTILITY BILL", "ELECTRICITY SERVICE", "AMOUNT DUE: 15000",
        "Provider: Review Energy",
    ])


def _ambiguous(api, token, run_id, label):
    return _upload_and_wait(api, token, run_id, label, [
        "UTILITY", "Name: Ambiguous Customer", "Reference: REVIEW-ONE",
    ])


@pytest.mark.catalogue("CL-TC-002", steps="1-4")
def test_CL_TC_002_classification_confidence_envelope(api, auth_token, run_id):
    result = _known_utility(api, auth_token, run_id, "cl002-confidence")
    classification = result["classification"]
    assert classification["family"] == "utility"
    assert 0 <= classification["confidence"] <= 1
    assert classification["configured_threshold"] == 0.5
    assert classification["review_required"] is False


@pytest.mark.catalogue("CL-TC-003", steps="1-5")
def test_CL_TC_003_ambiguous_classification_routes_to_review(api, auth_token, run_id):
    result = _ambiguous(api, auth_token, run_id, "cl003-ambiguous")
    assert result["classification"]["family"] == "unknown"
    assert result["classification"]["confidence"] < 1.0
    assert result["classification"]["review_required"] is True
    document = api.request("GET", f"/documents/{result['document_id']}", label="CL-TC-003 document routing", token=auth_token)
    assert document.status_code == 200 and document.json()["status"] == "needs_review"


@pytest.mark.catalogue("CL-TC-004", steps="1-5")
def test_CL_TC_004_same_family_documents_do_not_merge(api, auth_token, run_id):
    first = _known_utility(api, auth_token, run_id, "cl004-first")
    second = _known_utility(api, auth_token, run_id, "cl004-second")
    assert first["document_id"] != second["document_id"]
    assert first["classification"]["family"] == second["classification"]["family"] == "utility"
    listed = api.request("GET", "/documents", label="CL-TC-004 separate documents", token=auth_token)
    ids = {item["id"] for item in listed.json()}
    assert {first["document_id"], second["document_id"]} <= ids


@pytest.mark.catalogue("CL-TC-005", steps="1-4")
def test_CL_TC_005_confident_unknown_is_valid_outcome(api, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "cl005-unknown", [
        "COMMUNITY MEETING NOTICE", "Name: Example Person", "Reference: OOD-FIVE",
    ])
    assert result["classification"]["family"] == "unknown"
    assert result["classification"]["confidence"] == 1.0
    assert result["classification"]["review_required"] is False


@pytest.mark.catalogue("VA-TC-001", steps="1-4")
def test_VA_TC_001_ambiguous_fields_are_explicitly_uncertain(api, auth_token, run_id):
    result = _ambiguous(api, auth_token, run_id, "va001-uncertain")
    name = next(field for field in result["fields"] if field["field_name"] == "generic_name")
    assert name["value"] == "Ambiguous Customer"
    assert name["trust_state"] == "uncertain"


@pytest.mark.catalogue("VA-TC-002", steps="1-6")
def test_VA_TC_002_field_approval_waits_for_classification_review(api, auth_token, run_id):
    result = _ambiguous(api, auth_token, run_id, "va002-gate")
    field = next(field for field in result["fields"] if field["field_name"] == "generic_name")
    blocked = api.request("POST", f"/documents/{result['document_id']}/fields/{field['id']}/review", label="VA-TC-002 blocked field review", token=auth_token, json={"action": "confirm"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "classification_review_required"
    resolved = api.request("POST", f"/documents/{result['document_id']}/classification/review", label="VA-TC-002 resolve classification", token=auth_token, json={"action": "confirm"})
    assert resolved.status_code == 200
    assert resolved.json()["classification"]["review_required"] is False
    confirmed = api.request("POST", f"/documents/{result['document_id']}/fields/{field['id']}/review", label="VA-TC-002 field review after resolution", token=auth_token, json={"action": "confirm"})
    assert confirmed.status_code == 200


@pytest.mark.catalogue("VA-TC-003", steps="1-5")
def test_VA_TC_003_correction_persists_after_save(api, auth_token, run_id):
    result = _known_utility(api, auth_token, run_id, "va003-correction")
    amount = next(field for field in result["fields"] if field["field_name"] == "amount_due")
    saved = api.request("POST", f"/documents/{result['document_id']}/fields/{amount['id']}/review", label="VA-TC-003 save correction", token=auth_token, json={"action": "correct", "value": "75000"})
    assert saved.status_code == 200
    reopened = api.request("GET", f"/documents/{result['document_id']}/analysis", label="VA-TC-003 reopen", token=auth_token)
    current = next(field for field in reopened.json()["fields"] if field["id"] == amount["id"])
    assert current["value"] == "75000" and current["trust_state"] == "corrected"


@pytest.mark.catalogue("VA-TC-004", steps="1-5")
def test_VA_TC_004_correction_audit_does_not_retrain_model(api, auth_token, run_id):
    result = _known_utility(api, auth_token, run_id, "va004-audit")
    amount = next(field for field in result["fields"] if field["field_name"] == "amount_due")
    before = result["classification"]
    saved = api.request("POST", f"/documents/{result['document_id']}/fields/{amount['id']}/review", label="VA-TC-004 correction", token=auth_token, json={"action": "correct", "value": "76000"})
    assert saved.status_code == 200
    after = saved.json()["classification"]
    assert (after["provider"], after["model_version"], after["method"]) == (before["provider"], before["model_version"], before["method"])
    db = SessionLocal()
    try:
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == AuditEventType.CORRECTION, AuditEvent.target_id == amount["id"]).order_by(AuditEvent.created_at.desc()))
        assert event and event.metadata_json["field_name"] == "amount_due"
    finally:
        db.close()
