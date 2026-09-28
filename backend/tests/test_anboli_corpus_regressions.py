from app.models.enums import DocumentFamily
from app.services.analysis import classify_text, extract_predefined_fields


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
