from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "app" / "api" / "documents.py"
CONFIG = ROOT / "backend" / "app" / "core" / "config.py"
SCHEMAS = ROOT / "backend" / "app" / "schemas" / "documents.py"
WORKER = ROOT / "backend" / "app" / "workers" / "celery_app.py"
DOCUMENTS_PAGE = ROOT / "frontend" / "app" / "documents" / "page.tsx"


def test_processing_snapshot_exposes_stage_elapsed_and_stall_without_fabricated_percentage():
    api = API.read_text()
    schemas = SCHEMAS.read_text()

    assert "processing_stage: str | None" in schemas
    assert "processing_elapsed_seconds: int | None" in schemas
    assert "processing_active: bool" in schemas
    assert "processing_stalled: bool" in schemas
    assert "settings.processing_stalled_seconds" in api
    assert '"processing_stage": job.stage' in api
    assert "ProcessingJob.correlation_id == job.correlation_id" in api
    assert '"processing_started_at": started_at' in api
    assert "percent" not in schemas.lower()


def test_pipeline_has_bounded_timeout_and_commits_visible_page_stage_progress():
    config = CONFIG.read_text()
    worker = WORKER.read_text()

    assert "processing_soft_time_limit_seconds: int = 30 * 60" in config
    assert "processing_hard_time_limit_seconds: int = 31 * 60" in config
    assert "soft_time_limit=settings.processing_soft_time_limit_seconds" in worker
    assert "time_limit=settings.processing_hard_time_limit_seconds" in worker
    assert worker.count("job.updated_at = datetime.now(timezone.utc)") >= 3
    assert worker.count("db.commit()") >= 8


def test_document_list_refreshes_active_jobs_and_explains_stalled_or_failed_work():
    source = DOCUMENTS_PAGE.read_text()

    assert "document.processing_active" in source
    assert "window.setTimeout(() => load(page), 5000)" in source
    assert "Taking longer than expected" in source
    assert "Processing failed" in source
    assert "processing_elapsed_seconds" in source
    assert "d.processing_stalled ? 'Taking longer'" in source


def test_successful_pipeline_finalizes_document_instead_of_requeueing_it():
    worker = WORKER.read_text()

    assert (
        "document.status = ProcessingStatus.NEEDS_REVIEW "
        "if review_required else ProcessingStatus.READY"
    ) in worker
    assert (
        "document.status = ProcessingStatus.NEEDS_REVIEW "
        "if review_required else ProcessingStatus.QUEUED"
    ) not in worker
