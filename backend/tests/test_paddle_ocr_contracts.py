from __future__ import annotations

from io import BytesIO
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services import ocr


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (80, 40), "white").save(output, format="PNG")
    return output.getvalue()


class _Result:
    json = {
        "res": {
            "rec_texts": ["DOCUMENT ORGANIZER", "PP-TEST-2026-0001"],
            "rec_scores": [0.93, 0.87],
            "rec_boxes": [[2, 3, 42, 13], [4, 18, 64, 30]],
        }
    }


class _Pipeline:
    def predict(self, image):
        assert isinstance(image, ocr.np.ndarray)
        assert image.shape == (40, 80, 3)
        return [_Result()]


def test_paddle_pipeline_disables_broken_onednn_path(monkeypatch):
    captured = {}

    def fake_paddle_ocr(**kwargs):
        captured.update(kwargs)
        return _Pipeline()

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=fake_paddle_ocr))
    ocr._paddle_pipeline.cache_clear()
    try:
        pipeline = ocr._paddle_pipeline()
    finally:
        ocr._paddle_pipeline.cache_clear()

    assert isinstance(pipeline, _Pipeline)
    assert captured["enable_mkldnn"] is False
    assert captured["cpu_threads"] == 1


def test_paddle_result_is_normalized_to_existing_ocr_contract(monkeypatch):
    monkeypatch.setattr(ocr, "_paddle_pipeline", lambda: _Pipeline())
    result = ocr._recognize_with_paddle(_png())

    assert result.text == "DOCUMENT ORGANIZER\nPP-TEST-2026-0001"
    assert result.confidence == 0.9
    assert result.provider == "paddleocr"
    assert result.model_version == "PP-OCRv5_mobile_det+en_PP-OCRv5_mobile_rec"
    assert result.method == "printed_text_ocr"
    assert result.language == "en"
    assert result.blocks == [
        {
            "text": "DOCUMENT ORGANIZER",
            "confidence": 0.93,
            "bbox": {"x": 2, "y": 3, "width": 40, "height": 10},
        },
        {
            "text": "PP-TEST-2026-0001",
            "confidence": 0.87,
            "bbox": {"x": 4, "y": 18, "width": 60, "height": 12},
        },
    ]


def test_paddle_rejects_misaligned_result_arrays(monkeypatch):
    class BadResult:
        json = {"res": {"rec_texts": ["one"], "rec_scores": [], "rec_boxes": []}}

    class BadPipeline:
        def predict(self, image):
            return [BadResult()]

    monkeypatch.setattr(ocr, "_paddle_pipeline", lambda: BadPipeline())
    with pytest.raises(RuntimeError, match="misaligned"):
        ocr._recognize_with_paddle(_png())


def test_unknown_provider_fails_instead_of_silently_falling_back(monkeypatch):
    monkeypatch.setattr(ocr.settings, "ocr_provider", "not-a-provider")
    with pytest.raises(ValueError, match="Unsupported OCR provider"):
        ocr.recognize_page(_png())
