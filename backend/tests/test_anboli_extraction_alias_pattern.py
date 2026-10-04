"""Regressions for the reviewed Anboli alias/pattern extraction cycle."""

import pytest

from app.models.enums import DocumentFamily, TrustState
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
        (
            DocumentFamily.UTILITY,
            "Servie Connection Number\nTariff\nPhase\n02-501-009-2",
            "consumer_account_number",
            "02-501-009-2",
        ),
        (
            DocumentFamily.HOTEL,
            "Name\n: GOVARTHANAN KRISHNAMOORTY\nID No.\n: U0801712\nMember Card No.\n: 66956546",
            "guest_name",
            "GOVARTHANAN KRISHNAMOORTY",
        ),
        (
            DocumentFamily.INVOICE_RECEIPT,
            "Name of Customer(Billed to)\nAddress\nGSTIN\nGOVARTHANAN K",
            "customer_name",
            "GOVARTHANAN K",
        ),
        (
            DocumentFamily.INVOICE_RECEIPT,
            "TAX INVOICE\nOriginal for recipient\nInvoice date\nSupplier GSTIN\nJWGI25002928",
            "invoice_number",
            "JWGI25002928",
        ),
    ],
)
def test_reviewed_fields_extract_when_live_ocr_separates_label_and_value(
    family: DocumentFamily,
    text: str,
    field: str,
    expected: str,
):
    assert _values(family, text)[field] == expected


@pytest.mark.parametrize(
    ("family", "text", "field"),
    [
        (DocumentFamily.UTILITY, "Service Connection Number\nAmount Due\nDue Date", "consumer_account_number"),
        (DocumentFamily.HOTEL, "Name\nRoom\nCheck In\nCheck Out", "guest_name"),
        (DocumentFamily.HOTEL, "Name\nID No.\nNationality\nRoom", "guest_name"),
        (DocumentFamily.HOTEL, "Name\nID No.\nMember Card No.\nRoom", "guest_name"),
        (DocumentFamily.INVOICE_RECEIPT, "Name of Customer(Billed to)\nAddress\nTax\nTotal", "customer_name"),
        (DocumentFamily.INVOICE_RECEIPT, "TAX INVOICE\n17 Aug 2025\n59.00\nOriginal copy", "invoice_number"),
    ],
)
def test_separated_ocr_matching_rejects_neighbouring_headers_dates_and_amounts(
    family: DocumentFamily,
    text: str,
    field: str,
):
    assert _values(family, text)[field] is None


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
    ("text", "expected"),
    [
        (
            "UL 138 IXM 10:15:00.000 Srilankan Tue, 16 Dec, 2025",
            "16 Dec 2025",
        ),
        (
            "SIN 07:40 Singapore Saturday 18 Oct 2025 Changi Terminal 3",
            "18 Oct 2025",
        ),
    ],
)
def test_label_less_travel_date_fallback_extracts_unique_structured_candidate(
    text: str,
    expected: str,
):
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "UL 138\nIXM\n10:15:00.000\nSrilankan\nTue, 16 Dec, 2025",
            "16 Dec 2025",
        ),
        (
            "SIN\n07:40\nSingapore\nSaturday 18 Oct 2025\nChangi Terminal 3",
            "18 Oct 2025",
        ),
    ],
)
def test_label_less_travel_date_fallback_handles_adjacent_paddle_ocr_blocks(
    text: str,
    expected: str,
):
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] == expected


def test_label_less_travel_date_fallback_uses_first_live_ocr_departing_section():
    text = """
    11 Aug 2025
    1. SQ524 · Singapore to Chennai
    DEPARTING
    SIN 07:40
    MAA 09:20
    Singapore Airlines . SQ524
    Singapore
    Saturday 18 Oct 2025
    Saturday 18 Oct 2025
    Changi
    2. SQ529 · Chennai to Singapore
    DEPARTING
    MAA 23:25
    SIN 05:55
    Singapore Airlines . SQ529
    Singapore
    Saturday 01 Nov 2025
    Sunday 02 Nov 2025
    Changi
    """
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] == "18 Oct 2025"


def test_label_less_travel_date_fallback_abstains_for_ambiguous_first_departing_section():
    text = """
    DEPARTING
    SIN 23:25
    MAA 05:55
    Saturday 18 Oct 2025
    Sunday 19 Oct 2025
    DEPARTING
    MAA 07:40
    SIN 09:20
    Saturday 01 Nov 2025
    """
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] is None


def test_label_less_travel_date_fallback_is_low_confidence_and_inferred():
    text = "SIN 07:40 Singapore Saturday 18 Oct 2025 Changi Terminal 3"
    field = next(
        field
        for field in extract_predefined_fields(DocumentFamily.TRAVEL, text)
        if field.name == "departure_date"
    )
    assert field.value == "18 Oct 2025"
    assert field.confidence == 0.75
    assert field.trust_state == TrustState.INFERRED


def test_labelled_departure_date_wins_over_label_less_fallback():
    text = """
    Departure Date: 20 Dec 2025
    UL 138 IXM 10:15:00.000 Srilankan Tue, 16 Dec, 2025
    """
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] == "20 Dec 2025"


def test_label_less_travel_date_fallback_abstains_when_candidates_are_ambiguous():
    text = """
    UL 138 IXM 10:15:00 Srilankan Tue, 16 Dec, 2025
    UL 139 CMB 18:45:00 Srilankan Fri, 19 Dec, 2025
    """
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] is None


def test_label_less_travel_date_fallback_abstains_for_ambiguous_split_ocr_blocks():
    text = """
    UL 138
    IXM
    10:15:00
    Tue, 16 Dec, 2025
    UL 139
    CMB
    18:45:00
    Fri, 19 Dec, 2025
    """
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] is None


@pytest.mark.parametrize(
    "text",
    [
        "Terms updated on Tuesday 16 Dec 2025 for all passengers.",
        "Invoice Date: 18 Oct 2025",
        "Meeting at 07:40 on Saturday 18 Oct 2025.",
        "SIN 07:40 Singapore Friday 31 Feb 2025 Changi Terminal 3",
    ],
)
def test_label_less_travel_date_fallback_rejects_unstructured_dates(text: str):
    assert _values(DocumentFamily.TRAVEL, text)["departure_date"] is None


def test_label_less_travel_date_fallback_is_not_used_for_other_families():
    text = "SIN 07:40 Singapore Saturday 18 Oct 2025 Changi Terminal 3"
    values = _values(DocumentFamily.HOTEL, text)
    assert values["check_in"] is None
    assert values["check_out"] is None


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
