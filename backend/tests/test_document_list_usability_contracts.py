from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_PAGE = ROOT / "frontend" / "app" / "documents" / "page.tsx"


def test_document_selection_survives_pagination_for_one_bulk_export():
    source = DOCUMENTS_PAGE.read_text()

    assert "setSelected([])" not in source
    assert "Array.from(new Set([...current, ...pageIds]))" in source
    assert "Select this page" in source
    assert "Clear this page" in source


def test_processing_documents_can_be_deleted_from_the_list():
    source = DOCUMENTS_PAGE.read_text()

    assert "async function deleteDocument(document:Doc)" in source
    assert "method:'DELETE'" in source
    assert "onClick={()=>deleteDocument(d)}" in source
    assert "Permanently delete" in source
