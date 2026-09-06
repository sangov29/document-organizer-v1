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
