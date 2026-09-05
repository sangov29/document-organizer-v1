from app.models.enums import AuditEventType, DocumentFamily, TrustState


def test_v1_classification_outcomes_are_seven_known_plus_unknown():
    assert {x.value for x in DocumentFamily} == {
        "identity", "utility", "banking", "educational", "employment", "invoice_receipt", "travel", "unknown"
    }


def test_trust_state_is_explicit_six_state_model():
    assert {x.value for x in TrustState} == {"extracted", "uncertain", "not_found", "inferred", "confirmed", "corrected"}


def test_audit_event_catalogue_has_all_seven_mandatory_categories():
    assert {x.value for x in AuditEventType} == {
        "upload", "correction", "confirmation", "sensitive_reveal", "duplicate_override", "deletion", "auth_security"
    }
