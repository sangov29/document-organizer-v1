from __future__ import annotations

import base64
import json
import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditEvent
from app.models.enums import AuditEventType
from conftest import EVIDENCE_DIR, extract_token_from_mail, login, wait_for_mail_text
from test_cl_ex_runtime import _upload_and_wait


@pytest.mark.catalogue("SEC-TC-001", steps="1-12")
def test_SEC_TC_001_combined_financial_sensitive_data_protection(
    api, evidence, auth_token, email_factory, password_factory, run_id,
):
    account_number = "987654321012"
    analysis = _upload_and_wait(api, auth_token, run_id, "sec001-bank-slip", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        "Bank Name: Example Community Bank",
        "Account Holder: Synthetic Test Customer",
        f"Account Number: {account_number}",
        "Statement Date: 05 September 2026",
        "Signature: Synthetic Signature",
    ])
    document_id = analysis["document_id"]
    evidence.document(document_id)
    assert analysis["classification"]["family"] == "banking"
    account = {field["field_name"]: field for field in analysis["fields"]}["account_number"]
    assert account["sensitive"] is True
    assert account["sensitivity_type"] == "financial_account"
    assert account["masked"] is True
    assert account["value"].endswith(account_number[-4:])
    assert account_number not in json.dumps(analysis)
    assert account["provenance"]["visual_region_id"]

    signature = next(
        region for region in analysis["sensitive_regions"]
        if region["region_type"] == "signature"
    )
    assert signature["sensitivity_type"] == "signature"
    assert signature["concealed"] is True
    assert "content_base64" not in signature

    ocr = api.request(
        "GET", f"/documents/{document_id}/ocr",
        label="SEC-TC-001 OCR cannot bypass concealment", token=auth_token,
    )
    assert ocr.status_code == 200
    assert account_number not in json.dumps(ocr.json())
    assert "Synthetic Signature" not in json.dumps(ocr.json())
    assert "CONCEALED" in json.dumps(ocr.json())

    account_reveal = api.request(
        "POST", f"/documents/{document_id}/fields/{account['id']}/reveal",
        label="SEC-TC-001 explicit account reveal", token=auth_token,
    )
    assert account_reveal.status_code == 200
    assert account_reveal.headers["cache-control"] == "no-store, private"
    assert account_reveal.json()["revealed_value"] == account_number

    after_account = api.request(
        "GET", f"/documents/{document_id}/analysis",
        label="SEC-TC-001 refresh restores account mask", token=auth_token,
    )
    assert after_account.status_code == 200
    refreshed = {field["field_name"]: field for field in after_account.json()["fields"]}["account_number"]
    assert refreshed["masked"] is True and refreshed["value"] != account_number
    assert next(r for r in after_account.json()["sensitive_regions"] if r["id"] == signature["id"])["concealed"] is True

    signature_reveal = api.request(
        "POST", f"/documents/{document_id}/regions/{signature['id']}/reveal",
        label="SEC-TC-001 explicit signature reveal", token=auth_token,
    )
    assert signature_reveal.status_code == 200
    assert signature_reveal.headers["cache-control"] == "no-store, private"
    signature_png = base64.b64decode(signature_reveal.json()["content_base64"])
    assert signature_png.startswith(b"\x89PNG\r\n\x1a\n")

    email_b = email_factory("sec001-foreign")
    password_b = password_factory("sec001-foreign")
    assert api.request("POST", "/auth/register", label="SEC-TC-001 register foreign", json={"email": email_b, "password": password_b}).status_code == 202
    verification = extract_token_from_mail(wait_for_mail_text(email_b, subject_phrase="Verify"), "/verify-email")
    assert api.request("POST", "/auth/verify-email", label="SEC-TC-001 verify foreign", json={"token": verification}).status_code == 200
    foreign_login = login(api, email_b, password_b, label="SEC-TC-001 login foreign")
    assert foreign_login.status_code == 200
    foreign_token = foreign_login.json()["access_token"]
    foreign_field = api.request("POST", f"/documents/{document_id}/fields/{account['id']}/reveal", label="SEC-TC-001 foreign field denied", token=foreign_token)
    missing_field = api.request("POST", f"/documents/{document_id}/fields/{uuid.uuid4()}/reveal", label="SEC-TC-001 missing field", token=foreign_token)
    assert foreign_field.status_code == missing_field.status_code == 404
    assert foreign_field.json() == missing_field.json()
    foreign_region = api.request("POST", f"/documents/{document_id}/regions/{signature['id']}/reveal", label="SEC-TC-001 foreign region denied", token=foreign_token)
    missing_region = api.request("POST", f"/documents/{document_id}/regions/{uuid.uuid4()}/reveal", label="SEC-TC-001 missing region", token=foreign_token)
    assert foreign_region.status_code == missing_region.status_code == 404
    assert foreign_region.json() == missing_region.json()

    assert api.request("GET", "/audit", label="SEC-TC-001 audit access unavailable", token=auth_token).status_code == 404
    assert api.request("PATCH", f"/documents/{document_id}/fields/{account['id']}/reveal", label="SEC-TC-001 reveal audit edit unavailable", token=auth_token).status_code == 405
    assert api.request("DELETE", f"/documents/{document_id}/regions/{signature['id']}/reveal", label="SEC-TC-001 reveal audit delete unavailable", token=auth_token).status_code == 405

    db = SessionLocal()
    try:
        events = db.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == AuditEventType.SENSITIVE_REVEAL)
            .order_by(AuditEvent.created_at)
        ).all()
        owned = [event for event in events if event.target_id in {account["id"], signature["id"]}]
        assert len(owned) == 2
        audit_snapshot = [{
            "id": str(event.id), "user_id": str(event.user_id),
            "target_type": event.target_type, "target_id": event.target_id,
            "metadata": event.metadata_json, "created_at": event.created_at.isoformat(),
        } for event in owned]
        serialized_audit = json.dumps(audit_snapshot)
        assert account_number not in serialized_audit
        assert "content_base64" not in serialized_audit
    finally:
        db.close()

    evidence.note("sensitive-protection", {
        "document_id": document_id,
        "masked_account": account["value"],
        "signature_region_id": signature["id"],
        "foreign_denied": True,
        "audit_events": audit_snapshot,
    })
    folder = EVIDENCE_DIR / "security"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SEC-TC-001-result.json").write_text(json.dumps({
        "masked_account": account["value"],
        "account_region_id": account["provenance"]["visual_region_id"],
        "signature_region": signature,
        "audit_events": audit_snapshot,
    }, indent=2))
