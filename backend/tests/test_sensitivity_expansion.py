from app.services.sensitivity import sensitivity_type_for_field


def test_corpus_identifier_fields_are_marked_sensitive():
    expected = {
        "consumer_account_number": "financial_account",
        "loan_account": "financial_account",
        "document_number": "identity_number",
        "booking_reference": "travel_reference",
        "ticket_number": "travel_reference",
        "bill_of_lading": "shipping_reference",
        "container_number": "shipping_reference",
    }
    assert {name: sensitivity_type_for_field(name) for name in expected} == expected
