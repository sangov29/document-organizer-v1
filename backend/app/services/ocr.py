from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any

import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output

from app.core.config import settings


@dataclass(frozen=True)
class OCRPage:
    text: str
    confidence: float | None
    blocks: list[dict]
    provider: str
    model_version: str
    method: str
    language: str


def _recognize_with_tesseract(png: bytes) -> OCRPage:
    image = Image.open(BytesIO(png)).convert("RGB")
    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_tesseract_language,
        config=settings.ocr_tesseract_config,
        output_type=Output.DICT,
    )
    words: list[dict] = []
    line_words: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if not text or confidence < 0:
            continue
        bbox = {
            "x": int(data["left"][index]),
            "y": int(data["top"][index]),
            "width": int(data["width"][index]),
            "height": int(data["height"][index]),
        }
        words.append({"text": text, "confidence": round(confidence / 100.0, 4), "bbox": bbox})
        line_key = (int(data["block_num"][index]), int(data["par_num"][index]), int(data["line_num"][index]))
        line_words.setdefault(line_key, []).append(text)
        confidences.append(confidence / 100.0)

    text = "\n".join(" ".join(values) for values in line_words.values())
    mean_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    return OCRPage(
        text=text,
        confidence=mean_confidence,
        blocks=words,
        provider="tesseract",
        model_version="tesseract-5",
        method="printed_text_ocr",
        language=settings.ocr_tesseract_language,
    )


@lru_cache(maxsize=1)
def _paddle_pipeline():
    # Paddle is intentionally imported lazily: API processes and source-only
    # validation do not need to load the inference runtime or model weights.
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name=settings.ocr_paddle_detection_model,
        text_recognition_model_name=settings.ocr_paddle_recognition_model,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device=settings.ocr_paddle_device,
    )


def _paddle_payload(result: Any) -> dict[str, Any]:
    payload = result.json
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        raise RuntimeError("PaddleOCR returned a non-object result")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _recognize_with_paddle(png: bytes) -> OCRPage:
    # Paddle's ndarray input convention follows OpenCV (BGR).
    image = np.asarray(Image.open(BytesIO(png)).convert("RGB"))[:, :, ::-1].copy()
    results = list(_paddle_pipeline().predict(image))

    blocks: list[dict] = []
    lines: list[str] = []
    confidences: list[float] = []
    for result in results:
        payload = _paddle_payload(result)
        texts = payload.get("rec_texts", [])
        scores = payload.get("rec_scores", [])
        boxes = payload.get("rec_boxes", [])
        if not (len(texts) == len(scores) == len(boxes)):
            raise RuntimeError("PaddleOCR returned misaligned text, score and box arrays")
        for raw_text, raw_score, raw_box in zip(texts, scores, boxes):
            text = str(raw_text).strip()
            if not text:
                continue
            score = min(1.0, max(0.0, float(raw_score)))
            coordinates = [int(round(float(value))) for value in raw_box]
            if len(coordinates) != 4:
                raise RuntimeError("PaddleOCR returned an invalid recognition box")
            x_min, y_min, x_max, y_max = coordinates
            blocks.append({
                "text": text,
                "confidence": round(score, 4),
                "bbox": {
                    "x": x_min,
                    "y": y_min,
                    "width": max(0, x_max - x_min),
                    "height": max(0, y_max - y_min),
                },
            })
            lines.append(text)
            confidences.append(score)

    mean_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    return OCRPage(
        text="\n".join(lines),
        confidence=mean_confidence,
        blocks=blocks,
        provider="paddleocr",
        model_version=settings.ocr_model_version,
        method="printed_text_ocr",
        language=settings.ocr_language,
    )


def recognize_page(png: bytes) -> OCRPage:
    provider = settings.ocr_provider.strip().lower()
    if provider == "paddleocr":
        return _recognize_with_paddle(png)
    if provider == "tesseract":
        return _recognize_with_tesseract(png)
    raise ValueError(f"Unsupported OCR provider: {settings.ocr_provider!r}")
