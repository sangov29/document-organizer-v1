from __future__ import annotations

import json
from io import BytesIO

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services import preprocessing
from conftest import EVIDENCE_DIR, wait_for_preprocessing
from fixtures import document_png


def _save(name: str, data: bytes) -> str:
    folder = EVIDENCE_DIR / "preprocessing"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    return str(path.relative_to(EVIDENCE_DIR))


@pytest.mark.catalogue("PP-TC-001", steps="1-6")
def test_PP_TC_001_orientation_correction(monkeypatch, evidence, run_id):
    rows = []
    for source_rotation, correction in ((0, 0), (90, 270), (180, 180), (270, 90)):
        source = document_png(run_id, f"orientation-{source_rotation}", rotation=source_rotation)
        monkeypatch.setattr(preprocessing, "detect_orientation", lambda image, value=correction: (value, 20.0))
        result = preprocessing.preprocess_page(source, "image/png")
        before = _save(f"PP-TC-001-{source_rotation}-before.png", source)
        after = _save(f"PP-TC-001-{source_rotation}-after.png", result.png)
        rows.append({"input_rotation": source_rotation, "correction": result.orientation_degrees,
                     "confidence": result.orientation_confidence, "before": before, "after": after})
        assert result.orientation_degrees == correction
        assert not result.quality_metadata["orientation_uncertain"]

    ambiguous = document_png(run_id, "orientation-ambiguous", blur=12)
    monkeypatch.setattr(preprocessing, "detect_orientation", lambda image: (None, None))
    uncertain = preprocessing.preprocess_page(ambiguous, "image/png")
    assert uncertain.needs_review and uncertain.quality_metadata["orientation_uncertain"]
    evidence.note("orientation-before-after", rows)
    evidence.note("ambiguous-safe-routing", {"needs_review": uncertain.needs_review,
                                               "quality_status": uncertain.quality_status})


@pytest.mark.catalogue("PP-TC-002", steps="1-6")
def test_PP_TC_002_low_quality_detection_and_traceability(api, evidence, auth_token, run_id):
    body = document_png(run_id, "severe-low-contrast", contrast="low")
    response = api.request(
        "POST", "/documents", label="PP-TC-002 upload degraded page", token=auth_token,
        files={"file": ("low-contrast.png", body, "image/png")},
    )
    assert response.status_code == 202
    document_id = response.json()["id"]
    evidence.document(document_id)
    state = wait_for_preprocessing(document_id)
    page = state["pages"][0]
    evidence.note("quality-record", state)
    assert page["quality_status"] == "low_quality"
    assert page["needs_review"] is True
    assert state["document_status"] == "needs_review"
    assert page["quality_metadata"]["contrast_low"] is True
    assert page["page_id"] and page["normalized_object_key"]


@pytest.mark.catalogue("PP-TC-003", steps="1-5")
def test_PP_TC_003_deskew_supported_and_extreme_safe(monkeypatch, evidence, run_id):
    monkeypatch.setattr(preprocessing, "detect_orientation", lambda image: (0, 20.0))
    upright = document_png(run_id, "deskew-upright")
    mild = document_png(run_id, "deskew-mild", rotation=7)
    upright_result = preprocessing.preprocess_page(upright, "image/png")
    mild_result = preprocessing.preprocess_page(mild, "image/png")
    assert abs(upright_result.skew_degrees) < 1.0
    assert 2.0 < abs(mild_result.skew_degrees) <= preprocessing.settings.pp_deskew_max_degrees
    corrected_gray = cv2.cvtColor(np.array(Image.open(BytesIO(mild_result.png))), cv2.COLOR_RGB2GRAY)
    residual = preprocessing.detect_skew(corrected_gray)
    assert abs(residual) < 1.5

    monkeypatch.setattr(preprocessing, "detect_skew", lambda gray: preprocessing.settings.pp_deskew_max_degrees + 5)
    extreme = preprocessing.preprocess_page(upright, "image/png")
    assert extreme.needs_review and not extreme.quality_metadata["skew_supported"]
    evidence.note("deskew-measurements", {
        "upright": upright_result.skew_degrees,
        "mild_before": mild_result.skew_degrees,
        "mild_after": residual,
        "extreme": extreme.skew_degrees,
        "supported_tolerance": preprocessing.settings.pp_deskew_max_degrees,
    })
    _save("PP-TC-003-mild-before.png", mild)
    _save("PP-TC-003-mild-after.png", mild_result.png)


@pytest.mark.catalogue("PP-TC-004", steps="comparative feature decision")
def test_PP_TC_004_noise_reduction_defaults_disabled(evidence, run_id):
    result = preprocessing.preprocess_page(document_png(run_id, "noise-decision"), "image/png")
    assert preprocessing.settings.pp_noise_reduction_enabled is False
    assert result.noise_reduction_applied is False
    decision = {
        "decision": "disabled",
        "reason": "Could feature remains disabled until downstream OCR supplies paired recognition outcomes",
        "regression_risk_accepted": False,
    }
    evidence.note("noise-reduction-decision", decision)
    folder = EVIDENCE_DIR / "preprocessing"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PP-TC-004-decision.json").write_text(json.dumps(decision, indent=2))
