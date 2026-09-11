#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

from app.services.ocr import recognize_page


ROOT = Path("/acceptance")
CORPUS_PATH = ROOT / "ocr-eval" / "corpus.json"
EVIDENCE_DIR = Path(os.getenv("ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER", "/evidence"))
CER_MAX = float(os.getenv("OCR_EVAL_CER_MAX", "0.20"))
WER_MAX = float(os.getenv("OCR_EVAL_WER_MAX", "0.35"))


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def edit_distance(reference: list[str] | str, hypothesis: list[str] | str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, actual in enumerate(hypothesis, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (expected != actual),
            ))
        previous = current
    return previous[-1]


def error_rates(expected: str, actual: str) -> tuple[float, float]:
    normalized_expected = normalize(expected)
    normalized_actual = normalize(actual)
    cer = edit_distance(normalized_expected, normalized_actual) / max(1, len(normalized_expected))
    expected_words = normalized_expected.split()
    actual_words = normalized_actual.split()
    wer = edit_distance(expected_words, actual_words) / max(1, len(expected_words))
    return round(cer, 6), round(wer, 6)


def render(case: dict) -> bytes:
    from io import BytesIO

    width, height = 1400, 1100
    background = int(case.get("background", 250))
    foreground = int(case.get("foreground", 20))
    font_size = int(case.get("font_size", 38))
    spacing = int(case.get("line_spacing", 66))
    image = Image.new("RGB", (width, height), (background,) * 3)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    for index, line in enumerate(case["lines"]):
        draw.text((90, 90 + index * spacing), line, fill=(foreground,) * 3, font=font)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def main() -> int:
    corpus = json.loads(CORPUS_PATH.read_text())
    results = []
    total_chars = total_char_edits = total_words = total_word_edits = 0
    for case in corpus["cases"]:
        expected = "\n".join(case["lines"])
        started = time.perf_counter()
        recognition = recognize_page(render(case))
        latency = round(time.perf_counter() - started, 3)
        expected_normalized = normalize(expected)
        actual_normalized = normalize(recognition.text)
        char_edits = edit_distance(expected_normalized, actual_normalized)
        word_edits = edit_distance(expected_normalized.split(), actual_normalized.split())
        cer, wer = error_rates(expected, recognition.text)
        total_chars += len(expected_normalized)
        total_char_edits += char_edits
        total_words += len(expected_normalized.split())
        total_word_edits += word_edits
        passed = cer <= CER_MAX and wer <= WER_MAX
        results.append({
            "id": case["id"], "family": case["family"], "passed": passed,
            "character_error_rate": cer, "word_error_rate": wer,
            "confidence": recognition.confidence, "latency_seconds": latency,
            "provider": recognition.provider, "model_version": recognition.model_version,
            "expected_text": expected, "recognized_text": recognition.text,
        })

    aggregate_cer = round(total_char_edits / max(1, total_chars), 6)
    aggregate_wer = round(total_word_edits / max(1, total_words), 6)
    passed = all(item["passed"] for item in results) and aggregate_cer <= CER_MAX and aggregate_wer <= WER_MAX
    report = {
        "schema_version": "ocr-evaluation-v0.1",
        "corpus_version": corpus["version"],
        "claim_limit": corpus["description"],
        "thresholds": {"character_error_rate_max": CER_MAX, "word_error_rate_max": WER_MAX},
        "summary": {
            "passed": passed, "case_count": len(results),
            "character_error_rate": aggregate_cer, "word_error_rate": aggregate_wer,
            "mean_confidence": round(sum(item["confidence"] or 0 for item in results) / len(results), 6),
            "total_latency_seconds": round(sum(item["latency_seconds"] for item in results), 3),
        },
        "cases": results,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "ocr-evaluation.json").write_text(json.dumps(report, indent=2) + "\n")

    suite = ET.Element("testsuite", name="paddleocr-labelled-corpus", tests=str(len(results)),
                       failures=str(sum(not item["passed"] for item in results)))
    for item in results:
        test = ET.SubElement(suite, "testcase", classname="ocr.evaluation", name=item["id"],
                             time=str(item["latency_seconds"]))
        if not item["passed"]:
            failure = ET.SubElement(test, "failure", message="OCR accuracy threshold exceeded")
            failure.text = f"CER={item['character_error_rate']} WER={item['word_error_rate']}"
    ET.ElementTree(suite).write(EVIDENCE_DIR / "junit-ocr-evaluation.xml", encoding="utf-8", xml_declaration=True)

    print(f"PaddleOCR labelled corpus: {'PASS' if passed else 'FAIL'}")
    print(f"  cases={len(results)} CER={aggregate_cer:.4f} WER={aggregate_wer:.4f}")
    for item in results:
        print(f"  {item['id']}: {'PASS' if item['passed'] else 'FAIL'} "
              f"CER={item['character_error_rate']:.4f} WER={item['word_error_rate']:.4f} "
              f"confidence={item['confidence']} latency={item['latency_seconds']:.3f}s")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
