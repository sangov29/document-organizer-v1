from __future__ import annotations

import json
import time

import pytest

from conftest import EVIDENCE_DIR
from fixtures import document_png


@pytest.mark.catalogue("CR-TC-001", steps="1-6")
def test_CR_TC_001_printed_text_ocr_page_lineage(api, evidence, auth_token, run_id):
    source = document_png(run_id, "cr001-printed-text")
    upload = api.request(
        "POST", "/documents", label="CR-TC-001 upload printed page",
        token=auth_token, files={"file": ("printed-text.png", source, "image/png")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]
    evidence.document(document_id)

    deadline = time.time() + 90
    result = None
    while time.time() < deadline:
        response = api.request(
            "GET", f"/documents/{document_id}/ocr",
            label="CR-TC-001 poll public OCR", token=auth_token,
        )
        if response.status_code == 200:
            result = response.json()
            break
        assert response.status_code == 202
        time.sleep(0.5)
    assert result is not None, "Public OCR result did not become available"
    assert result["document_id"] == document_id
    assert len(result["pages"]) == 1
    page = result["pages"][0]
    normalized = " ".join(page["text"].upper().split())
    assert "DOCUMENT ORGANIZER ACCEPTANCE PAGE" in normalized
    assert "PP-TEST-2026-0001" in normalized
    assert page["page_number"] == 1 and page["page_id"]
    assert page["provider"] == "paddleocr"
    assert page["model_version"] == "PP-OCRv5_mobile_det+en_PP-OCRv5_mobile_rec"
    assert page["method"] == "printed_text_ocr"
    assert page["language"] == "en"
    assert page["processed_at"]
    assert page["confidence"] is not None and 0 <= page["confidence"] <= 1
    assert page["blocks"]
    assert all(
        block["text"] and 0 <= block["confidence"] <= 1
        and set(block["bbox"]) == {"x", "y", "width", "height"}
        for block in page["blocks"]
    )

    evidence.note("ocr-page-lineage", result)
    folder = EVIDENCE_DIR / "ocr"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "CR-TC-001-result.json").write_text(json.dumps(result, indent=2))


@pytest.mark.catalogue("CR-TC-002", steps="1-5")
def test_CR_TC_002_signature_region_detection(api, evidence, auth_token, email_factory, password_factory, run_id):
    import base64
    import uuid as uuid_lib

    from conftest import extract_token_from_mail, login, wait_for_mail_text
    from test_cl_ex_runtime import _upload_and_wait

    result = _upload_and_wait(api, auth_token, run_id, "cr002-bank-signature", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        "Bank Name: Example Community Bank",
        "Account Holder: Synthetic Test Customer",
        "Account Number: 555566667777",
        "Statement Date: 05 September 2026",
        "Signature: Synthetic Signature",
    ])
    document_id = result["document_id"]
    evidence.document(document_id)
    assert result["classification"]["family"] == "banking"

    signature = next(
        region for region in result["sensitive_regions"]
        if region["region_type"] == "signature"
    )
    assert signature["id"]
    assert signature["sensitivity_type"] == "signature"
    assert signature["concealed"] is True
    assert set(signature["bbox"]) == {"x", "y", "width", "height"}
    assert "content_base64" not in signature

    ocr = api.request(
        "GET", f"/documents/{document_id}/ocr",
        label="CR-TC-002 concealed OCR page lineage", token=auth_token,
    )
    assert ocr.status_code == 200
    page = ocr.json()["pages"][0]
    assert page["page_id"]
    assert page["provider"] and page["model_version"]
    assert page["confidence"] is not None and 0 <= page["confidence"] <= 1
    assert "Synthetic Signature" not in json.dumps(ocr.json())
    assert "CONCEALED" in json.dumps(ocr.json())

    owner_reveal = api.request(
        "POST", f"/documents/{document_id}/regions/{signature['id']}/reveal",
        label="CR-TC-002 owner reveal", token=auth_token,
    )
    assert owner_reveal.status_code == 200
    assert owner_reveal.headers["cache-control"] == "no-store, private"
    signature_png = base64.b64decode(owner_reveal.json()["content_base64"])
    assert signature_png.startswith(b"\x89PNG\r\n\x1a\n")

    email_b = email_factory("cr002-foreign")
    password_b = password_factory("cr002-foreign")
    assert api.request(
        "POST", "/auth/register", label="CR-TC-002 register foreign",
        json={"email": email_b, "password": password_b},
    ).status_code == 202
    verification = extract_token_from_mail(wait_for_mail_text(email_b, subject_phrase="Verify"), "/verify-email")
    assert api.request(
        "POST", "/auth/verify-email", label="CR-TC-002 verify foreign",
        json={"token": verification},
    ).status_code == 200
    foreign_login = login(api, email_b, password_b, label="CR-TC-002 login foreign")
    assert foreign_login.status_code == 200
    foreign_token = foreign_login.json()["access_token"]

    foreign_reveal = api.request(
        "POST", f"/documents/{document_id}/regions/{signature['id']}/reveal",
        label="CR-TC-002 foreign reveal denied", token=foreign_token,
    )
    missing_reveal = api.request(
        "POST", f"/documents/{document_id}/regions/{uuid_lib.uuid4()}/reveal",
        label="CR-TC-002 missing region", token=foreign_token,
    )
    assert foreign_reveal.status_code == missing_reveal.status_code == 404
    assert foreign_reveal.json() == missing_reveal.json()

    evidence.note("signature-region-detection", {
        "document_id": document_id,
        "signature_region_id": signature["id"],
        "foreign_denied": True,
    })
    folder = EVIDENCE_DIR / "content_recognition"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "CR-TC-002-result.json").write_text(json.dumps({
        "signature_region": signature,
        "foreign_denied": True,
    }, indent=2))
