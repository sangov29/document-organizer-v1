"""Focused regressions for Run #30's two implementation failures."""

import ast
from pathlib import Path

from app.models.enums import DocumentFamily, TrustState
from app.services.analysis import extract_predefined_fields


ROOT = Path(__file__).parents[1] / "app"


def test_inferred_field_preserves_last_character_and_trust_state():
    text = "\n".join([
        "PASSPORT",
        "Inferred Issuing Authority: External Registry Cross-Reference",
    ])
    fields = {
        field.name: field
        for field in extract_predefined_fields(DocumentFamily.IDENTITY, text)
    }
    assert fields["issuing_authority"].value == "External Registry Cross-Reference"
    assert fields["issuing_authority"].trust_state == TrustState.INFERRED


def test_analysis_serializer_queries_both_sensitive_region_tag_paths():
    source = (ROOT / "api" / "documents.py").read_text()
    tree = ast.parse(source)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_sensitive_regions_for_document"
    )
    helper_source = ast.unparse(helper)
    assert "SensitivityTag.visual_region_id == VisualRegion.id" in helper_source
    assert "Provenance.visual_region_id == VisualRegion.id" in helper_source
    assert "SensitivityTag.extracted_field_id == ExtractedField.id" in helper_source
    assert "serialized[region.id]" in helper_source
    assert "missing_ids" in helper_source
