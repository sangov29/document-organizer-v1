from __future__ import annotations

import json
import pytest
from conftest import EVIDENCE_DIR
from test_cl_ex_runtime import _upload_and_wait


@pytest.mark.catalogue("PR-TC-004", steps="1-6")
def test_PR_TC_004_correction_preserves_ai_history(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "pr004-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Account Holder: Test User",
        "Service Address: 10 Example Road", "Account Number: AC123456",
        "Amount Due: 15,000", "Due Date: 30 September 2026",
        "Provider: Example Energy",
    ])
    document_id = result["document_id"]
    fields = {field["field_name"]: field for field in result["fields"]}
    original = fields["amount_due"]
    original_provenance = original["provenance"]
    response = api.request(
        "POST", f"/documents/{document_id}/fields/{original['id']}/review",
        label="PR-TC-004 correct amount", token=auth_token,
        json={"action": "correct", "value": "75,000"},
    )
    assert response.status_code == 200
    corrected = {f["field_name"]: f for f in response.json()["fields"]}["amount_due"]
    assert corrected["value"] == "75,000"
    assert corrected["trust_state"] == "corrected"
    assert corrected["confidence"] is None
    assert corrected["provenance"] == original_provenance
    assert len(corrected["corrections"]) == 1
    history = corrected["corrections"][0]
    assert history["prior_value"] == "15,000"
    assert history["corrected_value"] == "75,000"
    assert history["user_id"] and history["created_at"]
    assert history["prior_provenance_id"] == original_provenance["id"]

    reopened = api.request("GET", f"/documents/{document_id}/analysis", label="PR-TC-004 reopen", token=auth_token)
    assert reopened.status_code == 200
    reopened_amount = {f["field_name"]: f for f in reopened.json()["fields"]}["amount_due"]
    assert reopened_amount == corrected

    confirm_target = fields["provider"]
    confirmed = api.request(
        "POST", f"/documents/{document_id}/fields/{confirm_target['id']}/review",
        label="PR-TC-004 confirm provider", token=auth_token,
        json={"action": "confirm"},
    )
    assert confirmed.status_code == 200
    assert {f["field_name"]: f for f in confirmed.json()["fields"]}["provider"]["trust_state"] == "confirmed"
    evidence.note("correction-before-after", {"before": original, "after": corrected})
    folder = EVIDENCE_DIR / "review"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PR-TC-004-result.json").write_text(json.dumps({"before": original, "after": corrected}, indent=2))


@pytest.mark.catalogue("PR-TC-001", steps="1-2")
def test_PR_TC_001_source_page(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "pr001-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Account Holder: Drew Example",
        "Service Address: 3 Example Terrace", "Account Number: AC334455",
        "Billing Period: August 2026", "Amount Due: 64.10",
        "Due Date: 25 October 2026", "Provider: Example Energy",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    assert result["fields"], "fixture must produce extracted fields"
    for field in result["fields"]:
        provenance = field["provenance"]
        assert provenance["source_document_id"] == document_id
        assert provenance["source_page_id"]
    evidence.note("source-page-provenance", result)
    folder = EVIDENCE_DIR / "provenance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PR-TC-001-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("PR-TC-002", steps="1-2")
def test_PR_TC_002_bounding_region(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "pr002-banking", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        "Bank Name: Example Regional Bank",
        "Account Holder: Drew Example",
        "Account Number: 998877665544",
        "Statement Date: 05 September 2026",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    account = {f["field_name"]: f for f in result["fields"]}["account_number"]
    region_id = account["provenance"]["visual_region_id"]
    assert region_id
    region = next(r for r in result["sensitive_regions"] if r["id"] == region_id)
    assert set(region["bbox"]) == {"x", "y", "width", "height"}
    assert all(isinstance(region["bbox"][key], int) for key in region["bbox"])
    assert all(region["bbox"][key] >= 0 for key in ("x", "y", "width", "height"))
    evidence.note("bounding-region-provenance", {"field": account, "region": region})
    folder = EVIDENCE_DIR / "provenance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PR-TC-002-result.json").write_text(json.dumps({"field": account, "region": region}, indent=2))


@pytest.mark.catalogue("PR-TC-003", steps="1-2")
def test_PR_TC_003_full_field_provenance(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "pr003-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Account Holder: Skyler Example",
        "Service Address: 21 Example Row", "Account Number: AC112200",
        "Billing Period: July 2026", "Amount Due: 41.75",
        "Due Date: 12 October 2026", "Provider: Example Energy",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    field = {f["field_name"]: f for f in result["fields"]}["amount_due"]
    provenance = field["provenance"]
    assert provenance["id"]
    assert provenance["source_document_id"] == document_id
    assert provenance["source_page_id"]
    assert provenance["provider"] == "builtin-rules"
    assert provenance["model_version"] == "schema-v0.1"
    assert provenance["method"] == "predefined_field_rules"
    assert provenance["confidence"] is not None and 0 <= provenance["confidence"] <= 1
    assert provenance["processed_at"]
    evidence.note("full-field-provenance", field)
    folder = EVIDENCE_DIR / "provenance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PR-TC-003-result.json").write_text(json.dumps(field, indent=2))


@pytest.mark.catalogue("PR-TC-005", steps="1-2")
def test_PR_TC_005_classification_provenance(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "pr005-unknown", [
        "RIVERSIDE ALLOTMENT SOCIETY NEWSLETTER",
        "Reference: PR005-001",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    classification = result["classification"]
    provenance = classification["provenance"]
    assert provenance["source_document_id"] == document_id
    assert provenance["source_page_id"]
    assert provenance["provider"] == classification["provider"]
    assert provenance["model_version"] == classification["model_version"]
    assert provenance["method"] == classification["method"]
    assert provenance["confidence"] is not None and 0 <= provenance["confidence"] <= 1
    assert provenance["processed_at"]
    evidence.note("classification-provenance", classification)
    folder = EVIDENCE_DIR / "provenance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PR-TC-005-result.json").write_text(json.dumps(classification, indent=2))


@pytest.mark.catalogue("PR-TC-006", steps="1-6")
def test_PR_TC_006_provenance_reconstruction_after_correction(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "pr006-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Account Holder: Reese Example",
        "Service Address: 8 Example Close", "Account Number: AC556677",
        "Billing Period: June 2026", "Amount Due: 30,000",
        "Due Date: 18 October 2026", "Provider: Example Energy",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    original_classification_provenance = result["classification"]["provenance"]
    fields = {f["field_name"]: f for f in result["fields"]}
    original = fields["amount_due"]
    original_field_provenance = original["provenance"]

    correction = api.request(
        "POST", f"/documents/{document_id}/fields/{original['id']}/review",
        label="PR-TC-006 correct amount", token=auth_token,
        json={"action": "correct", "value": "60,000"},
    )
    assert correction.status_code == 200
    corrected = {f["field_name"]: f for f in correction.json()["fields"]}["amount_due"]
    assert corrected["trust_state"] == "corrected"
    # The original model provenance record is retained unchanged; only the
    # active value/trust_state move, and the correction links back to it.
    assert corrected["provenance"] == original_field_provenance
    assert corrected["corrections"][0]["prior_provenance_id"] == original_field_provenance["id"]
    assert corrected["corrections"][0]["prior_value"] == "30,000"
    assert corrected["corrections"][0]["corrected_value"] == "60,000"

    reopened = api.request(
        "GET", f"/documents/{document_id}/analysis",
        label="PR-TC-006 reconstruct lineage", token=auth_token,
    )
    assert reopened.status_code == 200
    reopened_body = reopened.json()
    # Classification lineage is reconstructable and untouched by the field correction.
    assert reopened_body["classification"]["provenance"] == original_classification_provenance
    reopened_amount = {f["field_name"]: f for f in reopened_body["fields"]}["amount_due"]
    assert reopened_amount == corrected

    evidence.note("provenance-reconstruction-after-correction", {
        "classification_provenance": original_classification_provenance,
        "field_before": original,
        "field_after": corrected,
    })
    folder = EVIDENCE_DIR / "provenance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PR-TC-006-result.json").write_text(json.dumps({
        "classification_provenance": original_classification_provenance,
        "field_before": original,
        "field_after": corrected,
    }, indent=2))
