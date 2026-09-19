from __future__ import annotations

from datetime import date, datetime


REMINDER_FIELDS = {"expiry_date", "due_date", "payment_due_date"}
DATE_FORMATS = ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y")


def parse_document_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    return None


def reminder_status(days_remaining: int, due_soon_days: int = 30) -> str:
    if days_remaining < 0:
        return "overdue"
    if days_remaining <= due_soon_days:
        return "due_soon"
    return "upcoming"
