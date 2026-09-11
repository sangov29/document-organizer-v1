from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_worker_mounts_ocr_evaluation_inputs_and_evidence_output():
    compose = (ROOT / "acceptance" / "docker-compose.acceptance.yml").read_text()
    worker = compose.split("  worker:\n", 1)[1].split("  ui-tests:\n", 1)[0]

    assert "./acceptance:/acceptance:ro" in worker
    assert ":/evidence" in worker
    assert "ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER: /evidence" in worker


def test_ui_journey_uses_accessible_labels_not_visual_placeholder_copy():
    journey = (
        ROOT / "acceptance" / "ui" / "tests" / "document-journey.spec.ts"
    ).read_text()

    assert "getByLabel('Email address')" in journey
    assert "getByLabel('Password')" in journey
    assert "getByPlaceholder('Email')" not in journey
    assert "getByPlaceholder('Password (12+ chars)')" not in journey
    assert "getByText('Canonical document')" in journey
    assert "getByText('Duplicate of')" not in journey
