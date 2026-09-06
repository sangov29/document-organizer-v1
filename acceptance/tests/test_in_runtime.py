from __future__ import annotations

import csv
import io
import json

import pytest

from conftest import EVIDENCE_DIR
from test_cl_ex_runtime import _upload_and_wait


POLICY = "masked_no_bulk_reveal_v1"


def _utility(api, token, run_id, label):
    return _upload_and_wait(api, token, run_id, label, [
        "UTILITY BILL", "ELECTRICITY SERVICE", "AMOUNT DUE: 15000",
        "Account Holder: Synthetic Test Customer", "Provider: Example Energy",
    ])


@pytest.mark.catalogue("IN-TC-001", steps="1-8")
def test_IN_TC_001_stable_single_document_json_export(api, evidence, auth_token, run_id):
    analysis = _utility(api, auth_token, run_id, "in001-utility")
    document_id = analysis["document_id"]
    fields = {field["field_name"]: field for field in analysis["fields"]}
    correction = api.request(
        "POST", f"/documents/{document_id}/fields/{fields['amount_due']['id']}/review",
        label="IN-TC-001 correct amount", token=auth_token,
        json={"action": "correct", "value": "75000"},
    )
    assert correction.status_code == 200
    provider = {field["field_name"]: field for field in correction.json()["fields"]}["provider"]
    confirmation = api.request(
        "POST", f"/documents/{document_id}/fields/{provider['id']}/review",
        label="IN-TC-001 confirm provider", token=auth_token,
        json={"action": "confirm"},
    )
    assert confirmation.status_code == 200

    first = api.request("GET", f"/documents/{document_id}/export.json", label="IN-TC-001 JSON export", token=auth_token)
    second = api.request("GET", f"/documents/{document_id}/export.json", label="IN-TC-001 repeat JSON export", token=auth_token)
    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "no-store, private"
    assert first.content == second.content
    exported = first.json()
    assert exported["export_schema_version"] == "export-v0.1"
    assert exported["sensitive_export_policy"] == POLICY
    assert exported["document"]["id"] == document_id
    assert exported["classification"]["family"] == "utility"
    exported_fields = {field["field_name"]: field for field in exported["fields"]}
    assert exported_fields["amount_due"]["value"] == "75000"
    assert exported_fields["amount_due"]["trust_state"] == "corrected"
    assert exported_fields["amount_due"]["corrections"]
    assert exported_fields["provider"]["trust_state"] == "confirmed"
    assert exported_fields["billing_period"]["trust_state"] == "not_found"
    assert exported_fields["billing_period"]["value"] is None
    for field in exported["fields"]:
        assert field["provenance"]["source_document_id"] == document_id

    folder = EVIDENCE_DIR / "interoperability"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "IN-TC-001-export.json").write_text(json.dumps(exported, indent=2))
    (folder / "sensitive-export-policy.json").write_text(json.dumps({
        "policy": POLICY,
        "decision": "Sensitive values remain masked in JSON and CSV exports.",
        "unmasked_access": "Owner-only, audited single-subject reveal endpoints.",
        "bulk_unmasked_export": False,
    }, indent=2))


@pytest.mark.catalogue("IN-TC-002", steps="1-8")
def test_IN_TC_002_multi_document_csv_export(api, evidence, auth_token, run_id):
    utility = _utility(api, auth_token, run_id, "in002-utility")
    raw_account = "987654321012"
    banking = _upload_and_wait(api, auth_token, run_id, "in002-banking", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        "Account Holder: Synthetic Test Customer", f"Account Number: {raw_account}",
    ])
    ids = [utility["document_id"], banking["document_id"]]
    response = api.request(
        "POST", "/documents/batch/export.csv", label="IN-TC-002 CSV batch export",
        token=auth_token, json={"document_ids": ids},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert raw_account not in response.text
    reader = csv.DictReader(io.StringIO(response.text))
    expected_headers = [
        "export_schema_version", "sensitive_export_policy", "document_id",
        "original_filename", "family", "field_name", "value", "confidence",
        "trust_state", "criticality", "schema_version", "provider",
        "model_version", "method", "source_page_id", "visual_region_id",
        "sensitivity_type", "masked",
    ]
    assert reader.fieldnames == expected_headers
    rows = list(reader)
    assert {row["document_id"] for row in rows} == set(ids)
    assert {row["family"] for row in rows} == {"utility", "banking"}
    assert all(row["export_schema_version"] == "export-v0.1" for row in rows)
    assert all(row["sensitive_export_policy"] == POLICY for row in rows)
    not_found = [row for row in rows if row["trust_state"] == "not_found"]
    assert not_found and all(row["value"] == "" and row["confidence"] == "" for row in not_found)
    account = next(row for row in rows if row["field_name"] == "account_number")
    assert account["masked"] == "true" and account["value"].endswith(raw_account[-4:])

    folder = EVIDENCE_DIR / "interoperability"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "IN-TC-002-export.csv").write_text(response.text)
