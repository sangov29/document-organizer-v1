from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "evaluation" / "capture_live_corpus.py"


def test_capture_requires_exact_frozen_document_count_and_processes_annual_last():
    source = CAPTURE.read_text()

    assert 'default=12' in source
    assert '"annual" in path.name.casefold()' in source
    assert "Keep only the frozen corpus files in that folder" in source


def test_capture_records_masked_analysis_ocr_and_processed_dimensions_before_reveal():
    source = CAPTURE.read_text()

    assert '"analysis_before_reveal": True' in source
    assert '"processed_image_width"' in source
    assert '"processed_image_height"' in source
    assert '"masked_capture_complete"' in source
    assert "Starting separate reveal pass" in source


def test_runtime_endpoints_expose_geometry_needed_for_page_and_iou_scoring():
    api = (ROOT / "backend" / "app" / "api" / "documents.py").read_text()
    schemas = (ROOT / "backend" / "app" / "schemas" / "documents.py").read_text()

    assert "processed_image_width: int" in schemas
    assert "processed_image_height: int" in schemas
    assert "source_page_number: int | None" in schemas
    assert "visual_region_bbox: dict[str, int] | None" in schemas
    assert "PreprocessingResult.normalized_object_key" in api
    assert "select(VisualRegion.bbox)" in api


def test_capture_is_bounded_and_preserves_partial_evidence():
    source = CAPTURE.read_text()

    assert 'default=1800' in source
    assert '"capture_status"] = "failed"' in source
    assert 'write_json(args.output_dir / "raw-capture.json", capture)' in source
    assert 'return 0 if capture["summary"]["complete"] == args.expected_count else 1' in source


def test_capture_refuses_dirty_tree_and_records_commit_identity():
    source = CAPTURE.read_text()

    assert 'git_value("status", "--porcelain")' in source
    assert "Refusing to capture from a dirty working tree" in source
    assert 'git_value("rev-parse", "HEAD")' in source
    assert 'if branch != "main"' in source
    assert '"tree_clean": True' in source
