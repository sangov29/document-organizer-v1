from __future__ import annotations

import json
import time

import pytest

from conftest import EVIDENCE_DIR
from fixtures import document_png


def _upload_and_wait(api, token: str, run_id: str, label: str, lines: list[str]) -> dict:
    body = document_png(run_id, label, lines=[f"Run: {run_id} {label}", *lines])
    upload = api.request(
        "POST", "/documents", label=f"upload {label}", token=token,
        files={"file": (f"{label}.png", body, "image/png")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        response = api.request(
            "GET", f"/documents/{document_id}/analysis",
            label=f"poll analysis {label}", token=token,
        )
        if response.status_code == 200:
            return response.json()
        assert response.status_code == 202
        time.sleep(0.5)
    raise AssertionError(f"Analysis did not complete for {label}")


@pytest.mark.catalogue("CL-TC-001", steps="1-6")
def test_CL_TC_001_all_families_and_unknown(api, evidence, auth_token, run_id):
    fixtures = {
        "identity": ["PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH"],
        "utility": ["UTILITY BILL", "ELECTRICITY SERVICE", "AMOUNT DUE"],
        "banking": ["BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN"],
        "educational": ["ACADEMIC TRANSCRIPT", "UNIVERSITY", "CERTIFICATE"],
        "employment": ["EMPLOYMENT PAYSLIP", "SALARY", "EMPLOYER"],
        "invoice_receipt": ["TAX INVOICE", "RECEIPT", "TOTAL"],
        "travel": ["BOARDING PASS", "FLIGHT", "ITINERARY"],
        "unknown": ["COMMUNITY EVENT NOTICE", "MEETING ROOM FOUR", "REFERENCE ALPHA"],
    }
    results = {}
    for expected, lines in fixtures.items():
        result = _upload_and_wait(api, auth_token, run_id, f"cl001-{expected}", lines)
        evidence.document(result["document_id"])
        classification = result["classification"]
        assert classification["family"] == expected
        assert 0 <= classification["confidence"] <= 1
        assert classification["provider"] == "builtin-rules"
        assert classification["model_version"] == "keyword-v1"
        assert classification["method"] == "keyword_rules"
        assert classification["configured_threshold"] == 0.5
        provenance = classification["provenance"]
        assert provenance["source_document_id"] == result["document_id"]
        assert provenance["source_page_id"]
        assert provenance["provider"] == classification["provider"]
        assert provenance["model_version"] == classification["model_version"]
        assert provenance["method"] == classification["method"]
        assert provenance["processed_at"]
        results[expected] = result

    evidence.note("classification-outcomes", results)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "CL-TC-001-results.json").write_text(json.dumps(results, indent=2))


@pytest.mark.catalogue("EX-TC-009", steps="1-6")
def test_EX_TC_009_unknown_generic_extraction(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "ex009-unknown", [
        "COMMUNITY EVENT NOTICE",
        "Name: Alex Example",
        "Date: 05 September 2026",
        "Amount: 125.50",
        "Reference: UNKNOWN-001",
    ])
    evidence.document(result["document_id"])
    assert result["classification"]["family"] == "unknown"
    fields = {field["field_name"]: field for field in result["fields"]}
    assert set(fields) == {"generic_name", "generic_date", "generic_amount", "generic_address"}
    assert fields["generic_name"]["value"] == "Alex Example"
    assert fields["generic_date"]["value"] == "05 September 2026"
    assert fields["generic_amount"]["value"] == "125.50"
    assert fields["generic_address"]["value"] is None
    assert fields["generic_address"]["trust_state"] == "not_found"
    for field in fields.values():
        assert field["criticality"] == "standard"
        provenance = field["provenance"]
        assert provenance["source_document_id"] == result["document_id"]
        assert provenance["source_page_id"]
        assert provenance["provider"] and provenance["model_version"]
        assert provenance["method"] == "generic_unknown_rules"
        assert provenance["processed_at"]

    ocr = api.request(
        "GET", f"/documents/{result['document_id']}/ocr",
        label="EX-TC-009 Unknown OCR retention", token=auth_token,
    )
    assert ocr.status_code == 200
    assert "COMMUNITY EVENT NOTICE" in ocr.json()["pages"][0]["text"].upper()
    evidence.note("unknown-generic-extraction", result)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-009-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("EX-TC-008", steps="1-6")
def test_EX_TC_008_versioned_predefined_field_criticality(api, evidence, auth_token, run_id):
    fixtures = {
        "identity": [
            "PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH: 29 October 1988",
            "Full Name: Gov Test", "Passport Number: P1234567",
            "Issue Date: 01 January 2021", "Expiry Date: 01 January 2031",
            "Issuing Authority: Test Authority", "Nationality: Testland",
        ],
        "utility": [
            "UTILITY BILL", "ELECTRICITY SERVICE", "AMOUNT DUE: 125.50",
            "Account Holder: Gov Test", "Service Address: 10 Example Road",
            "Account Number: AC123456", "Due Date: 30 September 2026",
            "Provider: Example Energy",
        ],
    }
    expected = {
        "identity": {
            "full_name": "critical", "document_number": "critical",
            "date_of_birth": "critical", "issue_date": "standard",
            "expiry_date": "critical", "issuing_authority": "standard",
            "nationality": "standard",
        },
        "utility": {
            "account_holder": "critical", "service_address": "critical",
            "consumer_account_number": "critical", "billing_period": "standard",
            "amount_due": "critical", "due_date": "critical", "provider": "standard",
        },
    }
    results = {}
    for family, lines in fixtures.items():
        result = _upload_and_wait(api, auth_token, run_id, f"ex008-{family}", lines)
        assert result["classification"]["family"] == family
        fields = {field["field_name"]: field for field in result["fields"]}
        assert set(fields) == set(expected[family])
        for name, criticality in expected[family].items():
            field = fields[name]
            assert field["criticality"] == criticality
            assert field["schema_version"] == "schema-v0.1"
            assert field["trust_state"] in {"extracted", "not_found"}
            if field["trust_state"] == "extracted":
                assert field["value"] and 0 <= field["confidence"] <= 1
            else:
                assert field["value"] is None and field["confidence"] is None
            provenance = field["provenance"]
            assert provenance["source_document_id"] == result["document_id"]
            assert provenance["source_page_id"]
            assert provenance["model_version"] == "schema-v0.1"
            assert provenance["method"] == "predefined_field_rules"
        results[family] = result

    # Billing period is intentionally absent to prove a predefined field is
    # explicit not_found rather than omitted or represented as an empty value.
    utility_fields = {f["field_name"]: f for f in results["utility"]["fields"]}
    assert utility_fields["billing_period"]["trust_state"] == "not_found"
    evidence.note("versioned-predefined-fields", results)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-008-results.json").write_text(json.dumps(results, indent=2))
