from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[2] / "acceptance" / "tools" / "ocr_evaluation.py"
SPEC = spec_from_file_location("ocr_evaluation", SCRIPT)
assert SPEC and SPEC.loader
evaluation = module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def test_ocr_normalization_is_case_and_punctuation_tolerant():
    assert evaluation.normalize("Invoice No: INV-1042") == "invoice no inv 1042"
    assert evaluation.error_rates("Amount: 1,250.00", "amount 1 250 00") == (0.0, 0.0)


def test_ocr_error_rates_detect_substitution_insertion_and_deletion():
    cer, wer = evaluation.error_rates("one two three", "one too three extra")
    assert 0 < cer < 1
    assert wer == pytest.approx(2 / 3, abs=1e-6)


def test_ocr_error_rates_handle_empty_recognition():
    assert evaluation.error_rates("expected text", "") == (1.0, 1.0)
