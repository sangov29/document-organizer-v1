from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

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


def recognize_page(png: bytes) -> OCRPage:
    image = Image.open(BytesIO(png)).convert("RGB")
    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_language,
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
        provider=settings.ocr_provider,
        model_version=settings.ocr_model_version,
        method="printed_text_ocr",
        language=settings.ocr_language,
    )
