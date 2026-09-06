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


def test_invoice_receipt_schema_extracts_versioned_bounded_fields():
    text = "\n".join([
        "TAX INVOICE",
        "RECEIPT",
        "Vendor Name: Example Office Supplies",
        "Invoice Number: INV-2026-0042",
        "Invoice Date: 06 September 2026",
        "Customer Name: Example Customer",
        "Subtotal: 1,000.00",
        "Tax Amount: 180.00",
        "Total Amount: 1,180.00",
        "Currency: INR",
        "Purchase Order: PO-UNDEFINED",
    ])
    fields = {
        field.name: field
        for field in extract_predefined_fields(DocumentFamily.INVOICE_RECEIPT, text)
    }
    assert set(fields) == {
        "vendor_name", "invoice_number", "invoice_date", "customer_name",
        "subtotal", "tax_amount", "total_amount", "currency",
        "payment_due_date",
    }
    assert fields["invoice_number"].value == "INV-2026-0042"
    assert fields["invoice_date"].value == "06 September 2026"
    assert fields["total_amount"].value == "1,180.00"
    for name in ("invoice_number", "invoice_date", "total_amount"):
        assert fields[name].criticality == "critical"
        assert fields[name].trust_state == TrustState.EXTRACTED
        assert fields[name].schema_version == "schema-v0.1"
    assert fields["payment_due_date"].value is None
    assert fields["payment_due_date"].confidence is None
    assert fields["payment_due_date"].trust_state == TrustState.NOT_FOUND
    assert "purchase_order" not in fields


def test_invoice_receipt_aliases_preserve_receipt_values():
    fields = {
        field.name: field
        for field in extract_predefined_fields(
            DocumentFamily.INVOICE_RECEIPT,
            "\n".join([
                "RECEIPT",
                "Merchant: Corner Shop",
                "Receipt No: RCPT-77",
                "Receipt Date: 05 September 2026",
                "Grand Total: 75.50",
                "Currency: INR",
            ]),
        )
    }
    assert fields["vendor_name"].value == "Corner Shop"
    assert fields["invoice_number"].value == "RCPT-77"
    assert fields["invoice_date"].value == "05 September 2026"
    assert fields["total_amount"].value == "75.50"
