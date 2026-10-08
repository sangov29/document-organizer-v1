from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "app" / "api" / "documents.py"
SCHEMAS = ROOT / "backend" / "app" / "schemas" / "documents.py"
DOCUMENTS_PAGE = ROOT / "frontend" / "app" / "documents" / "page.tsx"
DETAIL_PAGE = ROOT / "frontend" / "app" / "documents" / "[id]" / "page.tsx"


def test_document_api_and_list_distinguish_processing_from_extraction_outcome():
    api = API.read_text()
    schemas = SCHEMAS.read_text()
    page = DOCUMENTS_PAGE.read_text()

    assert "structured_field_count: int = 0" in schemas
    assert "extracted_value_count: int = 0" in schemas
    assert "func.count(ExtractedField.value)" in api
    assert "Processing complete · no structured extraction fields are available." in page
    assert "Processing complete · no field values were extracted." in page


def test_detail_page_explains_zero_schema_fields_and_zero_values():
    source = DETAIL_PAGE.read_text()

    assert "analysis.fields.length === 0" in source
    assert "no structured extraction fields are available for this document family" in source
    assert "!analysis.fields.some(field => field.value != null)" in source
    assert "no field values were extracted" in source


def test_exports_version_and_preserve_selected_zero_field_documents():
    source = API.read_text()

    assert 'EXPORT_SCHEMA_VERSION = "export-v0.2"' in source
    assert '"document_status", "extraction_status"' in source
    assert 'return "no_schema_fields"' in source
    assert 'return "no_values_extracted"' in source
    assert "if not analysis.fields:" in source
    assert '"field_name": field.field_name' in source
