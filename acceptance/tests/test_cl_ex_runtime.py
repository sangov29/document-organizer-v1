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


@pytest.mark.catalogue("EX-TC-001", steps="1-3")
def test_EX_TC_001_predefined_family_fields(api, evidence, auth_token, run_id):
    fixtures = {
        "identity": (
            [
                "PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH: 12 May 1990",
                "Full Name: Alex Example", "Document Number: X1234567",
                "Issue Date: 01 January 2020", "Issuing Authority: Test Authority",
                "Nationality: Testland",
            ],
            {"full_name", "document_number", "date_of_birth", "issue_date",
             "expiry_date", "issuing_authority", "nationality"},
        ),
        "utility": (
            [
                "UTILITY BILL", "ELECTRICITY SERVICE", "Account Holder: Alex Example",
                "Service Address: 5 Sample Street", "Account Number: AC998877",
                "Amount Due: 200.00", "Due Date: 15 October 2026",
                "Provider: Sample Power",
            ],
            {"account_holder", "service_address", "consumer_account_number",
             "billing_period", "amount_due", "due_date", "provider"},
        ),
        "banking": (
            [
                "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
                "Bank Name: Example Bank", "Account Holder: Alex Example",
                "Account Number: 112233445566", "Statement Date: 01 September 2026",
            ],
            {"account_holder", "account_number", "bank_name", "statement_date"},
        ),
    }
    results = {}
    for family, (lines, expected_names) in fixtures.items():
        result = _upload_and_wait(api, auth_token, run_id, f"ex001-{family}", lines)
        evidence.document(result["document_id"])
        assert result["classification"]["family"] == family
        fields = {f["field_name"]: f for f in result["fields"]}
        assert set(fields) == expected_names, f"{family} schema fields mismatch"
        for field in fields.values():
            assert field["schema_version"] == "schema-v0.1"
        results[family] = result
    evidence.note("predefined-family-fields", results)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-001-results.json").write_text(json.dumps(results, indent=2))


@pytest.mark.catalogue("EX-TC-002", steps="1-2")
def test_EX_TC_002_field_confidence_bounds(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "ex002-identity", [
        "PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH: 03 March 1985",
        "Full Name: Sam Example", "Document Number: Y7654321",
        "Issue Date: 01 January 2019",
        # Expiry Date and Issuing Authority and Nationality intentionally omitted.
    ])
    evidence.document(result["document_id"])
    found_any_not_found = False
    for field in result["fields"]:
        if field["trust_state"] == "not_found":
            found_any_not_found = True
            assert field["value"] is None
            assert field["confidence"] is None
        else:
            assert field["value"] is not None
            assert field["confidence"] is not None
            assert 0 <= field["confidence"] <= 1
    assert found_any_not_found, "fixture must exercise at least one not_found field"
    evidence.note("field-confidence-bounds", result)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-002-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("EX-TC-003", steps="1-2")
def test_EX_TC_003_explicit_not_found_state(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "ex003-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Account Holder: Riley Example",
        "Service Address: 9 Sample Lane", "Account Number: AC554433",
        "Amount Due: 88.20", "Due Date: 20 October 2026",
        # Billing Period and Provider intentionally omitted.
    ])
    evidence.document(result["document_id"])
    fields = {f["field_name"]: f for f in result["fields"]}
    for name in ("billing_period", "provider"):
        assert fields[name]["trust_state"] == "not_found"
        assert fields[name]["value"] is None
        assert fields[name]["confidence"] is None
        assert fields[name]["schema_version"] == "schema-v0.1"
    evidence.note("explicit-not-found", result)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-003-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("EX-TC-004", steps="1-2")
def test_EX_TC_004_separate_inferred_information(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "ex004-identity", [
        "PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH: 14 July 1992",
        "Full Name: Jordan Example", "Document Number: Z9988776",
        "Issue Date: 01 January 2022", "Expiry Date: 01 January 2032",
        "Inferred Issuing Authority: External Registry Cross-Reference",
        "Nationality: Testland",
    ])
    evidence.document(result["document_id"])
    fields = {f["field_name"]: f for f in result["fields"]}
    inferred = fields["issuing_authority"]
    assert inferred["trust_state"] == "inferred"
    assert inferred["value"] == "External Registry Cross-Reference"
    assert inferred["confidence"] is not None and 0 <= inferred["confidence"] <= 1
    # Distinguishable from a directly OCR-extracted value on the same document.
    assert fields["full_name"]["trust_state"] == "extracted"
    assert inferred["trust_state"] != fields["full_name"]["trust_state"]
    evidence.note("separate-inferred-information", result)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-004-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("EX-TC-005", steps="1-3")
def test_EX_TC_005_confirm_inferred_field(api, evidence, auth_token, run_id):
    from app.db.session import SessionLocal
    from app.models import AuditEvent
    from app.models.enums import AuditEventType
    from sqlalchemy import select

    result = _upload_and_wait(api, auth_token, run_id, "ex005-identity", [
        "PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH: 21 April 1991",
        "Full Name: Casey Example", "Document Number: Q1122334",
        "Issue Date: 01 January 2021", "Expiry Date: 01 January 2031",
        "Inferred Issuing Authority: External Registry Cross-Reference",
        "Nationality: Testland",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    fields = {f["field_name"]: f for f in result["fields"]}
    inferred = fields["issuing_authority"]
    assert inferred["trust_state"] == "inferred"

    confirmed_response = api.request(
        "POST", f"/documents/{document_id}/fields/{inferred['id']}/review",
        label="EX-TC-005 confirm inferred field", token=auth_token,
        json={"action": "confirm"},
    )
    assert confirmed_response.status_code == 200
    confirmed = {f["field_name"]: f for f in confirmed_response.json()["fields"]}["issuing_authority"]
    assert confirmed["trust_state"] == "confirmed"
    assert confirmed["value"] == inferred["value"]

    db = SessionLocal()
    try:
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == AuditEventType.CONFIRMATION,
                AuditEvent.target_id == inferred["id"],
            )
        )
        assert event is not None
    finally:
        db.close()
    evidence.note("confirm-inferred-field", {"before": inferred, "after": confirmed})
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-005-result.json").write_text(json.dumps({"before": inferred, "after": confirmed}, indent=2))


@pytest.mark.catalogue("EX-TC-006", steps="1-2")
def test_EX_TC_006_bounded_schema_extraction(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "ex006-identity", [
        "PASSPORT", "IDENTITY DOCUMENT", "DATE OF BIRTH: 09 June 1993",
        "Full Name: Morgan Example", "Document Number: R5566778",
        "Issue Date: 01 January 2023", "Expiry Date: 01 January 2033",
        "Issuing Authority: Test Authority", "Nationality: Testland",
        "Blood Type: O Positive",  # plausible but undefined label for this family
        "Favourite Colour: Blue",  # another undefined label
    ])
    evidence.document(result["document_id"])
    expected_names = {
        "full_name", "document_number", "date_of_birth", "issue_date",
        "expiry_date", "issuing_authority", "nationality",
    }
    fields = {f["field_name"]: f for f in result["fields"]}
    assert set(fields) == expected_names
    assert "blood_type" not in fields
    assert "favourite_colour" not in fields
    for field in fields.values():
        assert field["schema_version"] == "schema-v0.1"
    evidence.note("bounded-schema-extraction", result)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-006-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("EX-TC-007", steps="1-3")
def test_EX_TC_007_preserve_unknown_ocr(api, evidence, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "ex007-unknown", [
        "NEIGHBOURHOOD GARDENING CLUB NOTICE",
        "Location: Community Hall Annex",
        "Reference: OOD-2026-EX007",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    assert result["classification"]["family"] == "unknown"
    ocr = api.request(
        "GET", f"/documents/{document_id}/ocr",
        label="EX-TC-007 unknown OCR retained", token=auth_token,
    )
    assert ocr.status_code == 200
    body = ocr.json()
    assert body["document_id"] == document_id
    page_text = body["pages"][0]["text"].upper()
    assert "NEIGHBOURHOOD GARDENING CLUB NOTICE" in page_text
    assert "OOD-2026-EX007" in page_text
    assert body["pages"][0]["page_id"]
    evidence.note("preserve-unknown-ocr", body)
    folder = EVIDENCE_DIR / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "EX-TC-007-result.json").write_text(json.dumps(body, indent=2))
