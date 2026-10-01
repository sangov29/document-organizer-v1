"""Regressions for the reviewed Anboli alias/pattern extraction cycle."""

import pytest

from app.models.enums import DocumentFamily
from app.services.analysis import extract_predefined_fields


def _values(family: DocumentFamily, text: str) -> dict[str, str | None]:
    return {
        field.name: field.value
        for field in extract_predefined_fields(family, text)
    }


@pytest.mark.parametrize(
    ("family", "text", "field", "expected"),
    [
        (
            DocumentFamily.TRAVEL,
            "Airline booking reference (PNR): A8DO7T, A8DO7T",
            "booking_reference",
            "A8DO7T",
        ),
        (
            DocumentFamily.TRAVEL,
            "Karthick Muruganathan         Ticket number: 6037397497674",
            "ticket_number",
            "6037397497674",
        ),
        (
            DocumentFamily.UTILITY,
            "Servie Connection Number                     02-501-009-2",
            "consumer_account_number",
            "02-501-009-2",
        ),
        (
            DocumentFamily.HOTEL,
            "Name                                                        : GOVARTHANAN KRISHNAMOORTY",
            "guest_name",
            "GOVARTHANAN KRISHNAMOORTY",
        ),
        (
            DocumentFamily.HOTEL,
            "Hotel Name:                      Resort Hotel",
            "property_name",
            "Resort Hotel",
        ),
        (
            DocumentFamily.INVOICE_RECEIPT,
            "Name of Customer(Billed to)          GOVARTHANAN K",
            "customer_name",
            "GOVARTHANAN K",
        ),
        (
            DocumentFamily.INVOICE_RECEIPT,
            "TAX INVOICE\n                                      JWGI25002928",
            "invoice_number",
            "JWGI25002928",
        ),
    ],
)
def test_reviewed_alias_and_pattern_cases_extract(
    family: DocumentFamily,
    text: str,
    field: str,
    expected: str,
):
    assert _values(family, text)[field] == expected


@pytest.mark.parametrize(
    ("family", "text", "field", "expected"),
    [
        (DocumentFamily.HOTEL, "Room Type: Deluxe Room", "room_type", "Deluxe Room"),
        (DocumentFamily.HOTEL, "Check In: 12 December 2025", "check_in", "12 December 2025"),
        (DocumentFamily.HOTEL, "Check Out: 15 December 2025", "check_out", "15 December 2025"),
        (DocumentFamily.INVOICE_RECEIPT, "Date of issue: 17 Aug 2025", "invoice_date", "17 Aug 2025"),
        (DocumentFamily.INVOICE_RECEIPT, "Customer Name: Govarthanan K", "customer_name", "Govarthanan K"),
    ],
)
def test_existing_correct_fields_do_not_regress(
    family: DocumentFamily,
    text: str,
    field: str,
    expected: str,
):
    assert _values(family, text)[field] == expected


@pytest.mark.parametrize(
    ("family", "text", "field"),
    [
        (
            DocumentFamily.TRAVEL,
            "Srilankan Tue, 16 Dec, 2025 Tue, 16 Dec, 2025",
            "departure_date",
        ),
        (
            DocumentFamily.TRAVEL,
            "Singapore Chennai\nSaturday 18 Oct 2025 Saturday 18 Oct 2025",
            "departure_date",
        ),
    ],
)
def test_label_less_travel_dates_remain_unextracted_in_this_cycle(
    family: DocumentFamily,
    text: str,
    field: str,
):
    """These two residual cases require layout support, not label matching."""
    assert _values(family, text)[field] is None


def test_embedded_matching_requires_a_label_boundary_and_delimiter():
    text = "Terms: your ticket number may be supplied later."
    assert _values(DocumentFamily.TRAVEL, text)["ticket_number"] is None


def test_invoice_header_fallback_rejects_prose_and_labelled_totals():
    text = "TAX INVOICE terms apply\nGrand Total: 111.18"
    assert _values(DocumentFamily.INVOICE_RECEIPT, text)["invoice_number"] is None


def test_generic_table_headers_do_not_become_field_values():
    text = """
    Total Amount       Discount       Taxable Amount
    1864.00            0.00           1864.00
    Tax                Currency       Total Amount
    0.00               SGD            SGD 175.00
    """
    values = _values(DocumentFamily.INVOICE_RECEIPT, text)
    assert values["tax_amount"] is None
    assert values["total_amount"] is None
