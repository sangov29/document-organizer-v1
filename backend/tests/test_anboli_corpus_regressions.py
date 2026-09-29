import json
from pathlib import Path

from app.models.enums import DocumentFamily
from app.services.analysis import classify_text, extract_predefined_fields


ROOT = Path(__file__).resolve().parents[2]


def test_catalogue_family_scope_matches_classifier_outcomes():
    coverage = json.loads((ROOT / "acceptance" / "coverage-map.json").read_text())
    scope = coverage["tests"]["CL-TC-001"]["family_scope"]
    fixtures = {
        "identity": "PASSPORT IDENTITY DOCUMENT DATE OF BIRTH",
        "utility": "UTILITY BILL ELECTRICITY SERVICE AMOUNT DUE",
        "banking": "BANK STATEMENT ACCOUNT STATEMENT IBAN",
        "educational": "ACADEMIC TRANSCRIPT UNIVERSITY CERTIFICATE",
        "employment": "EMPLOYMENT PAYSLIP SALARY EMPLOYER",
        "invoice_receipt": "TAX INVOICE RECEIPT TOTAL",
        "travel": "BOARDING PASS FLIGHT ITINERARY",
        "hotel": (
            "HOTEL CONFIRMATION\nROOM TYPE: Deluxe\n"
            "CHECK-IN: 12 December 2026\nCHECK-OUT: 15 December 2026"
        ),
    }

    assert scope["automatic"] == list(fixtures)
    for expected, text in fixtures.items():
        decision = classify_text(text)
        assert decision.family.value == expected
        assert decision.abstention_reason is None

    deferred_fixtures = {
        "legal_notice": "LEGAL NOTICE LOAN ACCOUNT OVERDUE AMOUNT",
        "shipping": "DELIVERY ORDER BILL OF LADING CONTAINER NUMBER",
    }
    assert set(scope["deferred"]) == set(deferred_fixtures)
    for family, text in deferred_fixtures.items():
        decision = classify_text(text)
        assert decision.family == DocumentFamily.UNKNOWN
        assert decision.abstention_reason == scope["deferred"][family]

    ood = classify_text("COMMUNITY EVENT NOTICE MEETING ROOM FOUR REFERENCE ALPHA")
    assert ood.family.value == scope["out_of_distribution"]["expected_family"]
    assert (
        ood.abstention_reason
        == scope["out_of_distribution"]["abstention_reason"]
    )


def test_hotel_terms_do_not_force_invoice_classification():
    text = """
    HOTEL BOOKING CONFIRMATION
    Guest: GOVARTHANAN KRISHNAMOORTHY
    Room Type: Deluxe Room
    Check-in: 12 December 2025
    Check-out: 15 December 2025
    Terms and conditions: retain your receipt. An invoice may be requested.
    Total: 0.00 MYR
    """
    decision = classify_text(text)
    assert decision.family == DocumentFamily.HOTEL
    assert decision.confidence < 1.0


def test_electricity_bill_is_utility_not_invoice():
    decision = classify_text("""
    ELECTRICITY BILL
    Service Connection: 02-501-009-2
    Meter Number: 17942929
    Invoice Number: L416260962768230
    Amount Due: Rs.0/-
    """)
    assert decision.family == DocumentFamily.UTILITY


def test_airline_eticket_receipt_is_travel_not_invoice():
    decision = classify_text("""
    E-TICKET RECEIPT
    Booking Reference: EF6IGU
    Ticket Number: 618-2467306332
    Flight: SQ524
    Grand Total: SGD 528.40
    """)
    assert decision.family == DocumentFamily.TRAVEL


def test_single_generic_invoice_word_abstains():
    decision = classify_text("Terms: an invoice may be requested after your stay")
    assert decision.family == DocumentFamily.UNKNOWN
    assert decision.confidence < 1.0
    assert decision.abstention_reason == "insufficient_distinctive_evidence"


def test_no_known_family_evidence_abstains_at_review_threshold():
    decision = classify_text(
        "COMMUNITY EVENT NOTICE MEETING ROOM FOUR REFERENCE ALPHA"
    )
    assert decision.family == DocumentFamily.UNKNOWN
    assert decision.confidence == 0.5
    assert decision.abstention_reason == "no_known_family_evidence"


def test_unstructured_third_party_booking_remains_unknown():
    decision = classify_text("""
    Booking Confirmation
    Please present this confirmation upon check-in.
    Arrival: 19 October 2025
    Departure: 20 October 2025
    Room Type: Deluxe
    Cancellation Policy: Risk-free booking.
    """)
    assert decision.family == DocumentFamily.UNKNOWN
    assert decision.abstention_reason == "hotel_confirmation_without_required_structured_stay_date_labels"


def test_legal_and_shipping_schemas_do_not_auto_promote_in_this_cycle():
    legal = classify_text("LOAN ACCOUNT: 123 OVERDUE AMOUNT: 100 DEFAULT NOTICE")
    shipping = classify_text("DELIVERY ORDER CONTAINER NO: ABC123 VESSEL: TEST")
    assert legal.family == DocumentFamily.UNKNOWN
    assert shipping.family == DocumentFamily.UNKNOWN
    assert legal.abstention_reason == "family_schema_available_but_auto_classification_deferred"
    assert shipping.abstention_reason == "family_schema_available_but_auto_classification_deferred"


def test_new_families_have_bounded_versioned_schemas():
    expectations = {
        DocumentFamily.TRAVEL: {"booking_reference", "ticket_number", "passenger_name", "origin", "destination", "departure_date", "flight_number", "total_amount"},
        DocumentFamily.HOTEL: {"booking_number", "guest_name", "property_name", "room_type", "check_in", "check_out", "total_amount"},
        DocumentFamily.LEGAL_NOTICE: {"notice_reference", "notice_date", "recipient", "institution", "loan_account", "overdue_amount", "payment_deadline"},
        DocumentFamily.SHIPPING: {"job_number", "customer_name", "bill_of_lading", "origin", "vessel", "eta", "container_number", "weight_kg", "amount_due"},
    }
    for family, expected in expectations.items():
        fields = extract_predefined_fields(family, "")
        assert {field.name for field in fields} == expected
        assert all(field.schema_version == "schema-v0.2" for field in fields)


def test_annual_report_remains_unknown_in_this_fix_cycle():
    decision = classify_text(
        "ANNUAL REPORT 2025-26 CORPORATE INFORMATION BOARD OF DIRECTORS"
    )
    assert decision.family == DocumentFamily.UNKNOWN
    assert decision.confidence == 0.5
    assert decision.abstention_reason == "out_of_scope_family"
