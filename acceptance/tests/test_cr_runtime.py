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
    assert page["provider"] == "tesseract"
    assert page["model_version"] and page["method"] == "printed_text_ocr"
    assert page["language"] == "eng"
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
