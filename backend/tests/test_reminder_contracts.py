from datetime import date

from app.services.reminders import parse_document_date, reminder_status


def test_document_date_parser_is_explicit_and_non_ambiguous():
    assert parse_document_date("2030-01-31") == date(2030, 1, 31)
    assert parse_document_date("31 January 2030") == date(2030, 1, 31)
    assert parse_document_date("31 Jan 2030") == date(2030, 1, 31)
    assert parse_document_date("31/01/2030") == date(2030, 1, 31)
    assert parse_document_date("01/31/2030") is None
    assert parse_document_date("not a date") is None


def test_reminder_status_boundaries():
    assert reminder_status(-1) == "overdue"
    assert reminder_status(0) == "due_soon"
    assert reminder_status(30) == "due_soon"
    assert reminder_status(31) == "upcoming"


def test_reminder_query_is_owner_scoped_and_active_field_only():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "documents.py").read_text()
    assert "Document.user_id == user.id" in source
    assert "ExtractedField.is_active.is_(True)" in source
    assert "ExtractedField.field_name.in_(REMINDER_FIELDS)" in source
    assert "_current_document_clause()" in source
