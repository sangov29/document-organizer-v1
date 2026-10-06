from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_PAGE = ROOT / "frontend" / "app" / "documents" / "page.tsx"


def test_upload_controls_reset_immediately_and_allow_the_next_selection():
    source = DOCUMENTS_PAGE.read_text()

    assert "form.reset(); setSingleFileName('');" in source
    assert "form.reset(); setBulkFileNames([]);" in source
    assert "You can choose and upload more files while these documents process." in source
    assert "disabled={!ready}" in source
    assert "disabled={!ready ||" not in source


def test_upload_activity_reports_each_file_without_erasing_duplicates():
    source = DOCUMENTS_PAGE.read_text()

    assert "type UploadActivity" in source
    assert "Uploading to the secure queue" in source
    assert "Queued for background processing" in source
    assert "Duplicate detected. Choose whether to keep another copy." in source
    assert "fd.set('duplicate_action', 'keep')" in source
    assert "activities.find(activity => activity.id === item.id)" in source


def test_selected_filenames_are_visible_before_submission():
    source = DOCUMENTS_PAGE.read_text()

    assert "singleFileName || 'Choose PDF, JPG or PNG'" in source
    assert "bulkFileNames.join(', ')" in source
    assert "setSingleFileName(event.target.files?.[0]?.name ?? '')" in source
    assert "setBulkFileNames(Array.from(event.target.files ?? []).map(file=>file.name))" in source


def test_upload_activity_ids_do_not_require_random_uuid_browser_support():
    source = DOCUMENTS_PAGE.read_text()

    assert "const createUploadId = () =>" in source
    assert "id:createUploadId()" in source
    assert "crypto.randomUUID" not in source
