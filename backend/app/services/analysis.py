from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.core.config import settings
from app.models.enums import DocumentFamily, TrustState


PROVIDER = "builtin-rules"
MODEL_VERSION = "keyword-v2"
METHOD = "keyword_rules"
SCHEMA_VERSION = "schema-v0.2"

FAMILY_MARKERS: dict[DocumentFamily, tuple[tuple[str, float], ...]] = {
    DocumentFamily.IDENTITY: (("PASSPORT", 1.0), ("IDENTITY DOCUMENT", 1.0), ("DATE OF BIRTH", 0.5)),
    DocumentFamily.UTILITY: (("UTILITY BILL", 1.0), ("ELECTRICITY", 1.0), ("POWER DISTRIBUTION", 1.0), ("CURRENT CONSUMPTION", 1.0), ("SERVICE CONNECTION", 0.75), ("SERVIE CONNECTION", 0.75), ("METER NUMBER", 0.75), ("METER NO", 0.75), ("BILL PERIOD", 0.75), ("BILL AMOUNT", 0.5), ("AMOUNT DUE", 0.5)),
    DocumentFamily.BANKING: (("BANK STATEMENT", 1.0), ("ACCOUNT STATEMENT", 1.0), ("IBAN", 0.75)),
    DocumentFamily.EDUCATIONAL: (("ACADEMIC TRANSCRIPT", 1.0), ("UNIVERSITY", 0.75), ("CERTIFICATE", 0.5)),
    DocumentFamily.EMPLOYMENT: (("PAYSLIP", 1.0), ("EMPLOYMENT", 0.75), ("SALARY", 0.5)),
    DocumentFamily.INVOICE_RECEIPT: (("TAX INVOICE", 1.0), ("GST INVOICE", 1.0), ("INVOICE NUMBER", 0.75), ("INVOICE NO", 0.75), ("RECEIPT NUMBER", 0.75), ("BILL TO", 0.5), ("TAX AMOUNT", 0.5), ("AMOUNT DUE", 0.5), ("SUBTOTAL", 0.5), ("GRAND TOTAL", 0.5), ("GST", 0.5), ("INVOICE", 0.15), ("RECEIPT", 0.15), ("TOTAL", 0.15)),
    DocumentFamily.TRAVEL: (("BOARDING PASS", 1.0), ("E-TICKET", 1.0), ("ETICKET", 1.0), ("ITINERARY", 1.0), ("FLIGHT", 0.5), ("TICKET NUMBER", 0.75), ("BOOKING REFERENCE", 0.75)),
    DocumentFamily.HOTEL: (("HOTEL CONFIRMATION", 1.0), ("BOOKING CONFIRMATION", 1.0), ("CHECK-IN", 0.75), ("CHECK IN", 0.75), ("CHECK-OUT", 0.75), ("CHECK OUT", 0.75), ("ROOM TYPE", 0.75), ("GUEST", 0.5)),
    DocumentFamily.LEGAL_NOTICE: (("LEGAL NOTICE", 1.0), ("NOTICE REFERENCE", 0.75), ("LOAN ACCOUNT", 0.75), ("OVERDUE AMOUNT", 0.75), ("DEFAULT", 0.5)),
    DocumentFamily.SHIPPING: (("DELIVERY ORDER", 1.0), ("BILL OF LADING", 1.0), ("CONTAINER NUMBER", 0.75), ("CONTAINER NO", 0.75), ("VESSEL", 0.5), ("PORT OF LOADING", 0.5)),
}

DISTINCTIVE_MARKERS = {
    family: {marker for marker, weight in markers if weight >= 0.75}
    for family, markers in FAMILY_MARKERS.items()
}

FAMILY_NEGATIVE_MARKERS: dict[DocumentFamily, tuple[str, ...]] = {
    DocumentFamily.INVOICE_RECEIPT: (
        "TERMS AND CONDITIONS",
        "CANCELLATION POLICY",
        "RESERVATION",
        "CHECK-IN",
        "CHECK IN",
        "ROOM TYPE",
    ),
}

GENERIC_PATTERNS = {
    "generic_name": re.compile(r"^\s*name\s*:\s*(.+?)\s*$", re.I | re.M),
    "generic_date": re.compile(r"^\s*date\s*:\s*(.+?)\s*$", re.I | re.M),
    "generic_amount": re.compile(r"^\s*amount\s*:\s*(.+?)\s*$", re.I | re.M),
    "generic_address": re.compile(r"^\s*address\s*:\s*(.+?)\s*$", re.I | re.M),
}

# These schemas are available for extraction after a reviewed/manual family
# assignment, but the current single-reviewer corpus is not broad enough to
# enable automatic promotion for legal notices or shipping documents.
AUTO_CLASSIFY_ENABLED_FAMILIES = set(FAMILY_MARKERS) - {
    DocumentFamily.LEGAL_NOTICE,
    DocumentFamily.SHIPPING,
}


def _has_family_promotion_evidence(family: DocumentFamily, text: str) -> bool:
    if family not in AUTO_CLASSIFY_ENABLED_FAMILIES:
        return False
    if family == DocumentFamily.HOTEL:
        # Prose mentions of check-in, cancellation, or booking confirmation
        # are common on third-party reservation pages. Require structured stay
        # dates before automatically naming the document as a hotel record.
        has_check_in = re.search(r"^\s*check[ -]?in\s*:\s*\S", text, re.I | re.M)
        has_check_out = re.search(r"^\s*check[ -]?out\s*:\s*\S", text, re.I | re.M)
        return bool(has_check_in and has_check_out)
    return True

PREDEFINED_SCHEMAS: dict[DocumentFamily, dict[str, tuple[str, tuple[str, ...]]]] = {
    DocumentFamily.IDENTITY: {
        "full_name": ("critical", ("Full Name", "Name")),
        "document_number": ("critical", ("Document Number", "Passport Number", "ID Number")),
        "date_of_birth": ("critical", ("Date of Birth", "DOB")),
        "issue_date": ("standard", ("Issue Date", "Date of Issue")),
        "expiry_date": ("critical", ("Expiry Date", "Date of Expiry")),
        "issuing_authority": ("standard", ("Issuing Authority", "Authority")),
        "nationality": ("standard", ("Nationality",)),
    },
    DocumentFamily.UTILITY: {
        "account_holder": ("critical", ("Account Holder", "Customer Name")),
        "service_address": ("critical", ("Service Address", "Supply Address")),
        "consumer_account_number": (
            "critical",
            (
                "Consumer Number",
                "Account Number",
                "Service Connection Number",
                "Servie Connection Number",
            ),
        ),
        "billing_period": ("standard", ("Billing Period",)),
        "amount_due": ("critical", ("Amount Due",)),
        "due_date": ("critical", ("Due Date",)),
        "provider": ("standard", ("Provider", "Service Provider")),
    },
    DocumentFamily.BANKING: {
        "account_holder": ("critical", ("Account Holder", "Customer Name")),
        "account_number": ("critical", ("Account Number",)),
        "bank_name": ("standard", ("Bank Name", "Bank")),
        "statement_date": ("standard", ("Statement Date",)),
    },
    DocumentFamily.INVOICE_RECEIPT: {
        "vendor_name": ("standard", ("Vendor Name", "Supplier", "Merchant")),
        "invoice_number": (
            "critical",
            ("Invoice Number", "Invoice No", "Receipt Number", "Receipt No"),
        ),
        "invoice_date": ("critical", ("Invoice Date", "Receipt Date", "Date of issue", "Date")),
        "customer_name": (
            "standard",
            ("Customer Name", "Bill To", "Name of Customer(Billed to)"),
        ),
        "subtotal": ("standard", ("Subtotal", "Sub Total")),
        "tax_amount": ("standard", ("Tax Amount", "Tax", "GST", "VAT")),
        "total_amount": ("critical", ("Total Amount after Tax", "Total Amount", "Grand Total", "Amount Due", "Total")),
        "currency": ("standard", ("Currency",)),
        "payment_due_date": ("standard", ("Payment Due Date", "Due Date")),
    },
    DocumentFamily.TRAVEL: {
        "booking_reference": ("critical", ("Booking Reference", "Booking ID", "PNR")),
        "ticket_number": ("critical", ("Ticket Number", "E-Ticket Number")),
        "passenger_name": ("critical", ("Passenger", "Passenger Name")),
        "origin": ("standard", ("Origin", "From")),
        "destination": ("standard", ("Destination", "To")),
        "departure_date": ("critical", ("Departure Date", "Travel Date")),
        "flight_number": ("standard", ("Flight", "Flight Number")),
        "total_amount": ("standard", ("Grand Total", "Total Amount")),
    },
    DocumentFamily.HOTEL: {
        "booking_number": ("critical", ("Booking Number", "Booking ID", "Confirmation Number")),
        "guest_name": ("critical", ("Guest", "Guest Name", "Client", "Name")),
        "property_name": (
            "critical",
            ("Hotel", "Hotel Name", "Property", "Property Name"),
        ),
        "room_type": ("standard", ("Room Type", "Room")),
        "check_in": ("critical", ("Check-in", "Check In", "Arrival Date")),
        "check_out": ("critical", ("Check-out", "Check Out", "Departure Date")),
        "total_amount": ("standard", ("Total Amount", "Grand Total")),
    },
    DocumentFamily.LEGAL_NOTICE: {
        "notice_reference": ("critical", ("Notice Reference", "Reference")),
        "notice_date": ("critical", ("Notice Date", "Date")),
        "recipient": ("critical", ("Recipient", "To")),
        "institution": ("standard", ("Bank", "Institution")),
        "loan_account": ("critical", ("Loan Account", "Loan Account Number")),
        "overdue_amount": ("critical", ("Overdue Amount", "Amount Due")),
        "payment_deadline": ("standard", ("Payment Deadline", "Pay Within")),
    },
    DocumentFamily.SHIPPING: {
        "job_number": ("critical", ("Job Number", "Job No", "Job Reference")),
        "customer_name": ("standard", ("Customer", "Customer Name")),
        "bill_of_lading": ("critical", ("Bill of Lading", "B/L Number")),
        "origin": ("standard", ("Origin", "Port of Loading")),
        "vessel": ("standard", ("Vessel", "Vessel Name")),
        "eta": ("standard", ("ETA", "Arrival Date")),
        "container_number": ("critical", ("Container Number", "Container No")),
        "weight_kg": ("standard", ("Weight", "Weight Kg")),
        "amount_due": ("standard", ("Amount Due", "Total Amount")),
    },
}


@dataclass(frozen=True)
class ClassificationDecision:
    family: DocumentFamily
    confidence: float
    abstention_reason: str | None = None
    provider: str = PROVIDER
    model_version: str = MODEL_VERSION
    method: str = METHOD


@dataclass(frozen=True)
class GenericFieldDecision:
    name: str
    value: str | None
    confidence: float | None
    trust_state: TrustState
    criticality: str = "standard"
    schema_version: str | None = None


def classify_text(text: str) -> ClassificationDecision:
    normalized = " ".join(text.upper().split())
    if "ANNUAL REPORT" in normalized:
        return ClassificationDecision(
            DocumentFamily.UNKNOWN,
            settings.classification_known_threshold,
            "out_of_scope_family",
        )
    evidence: dict[DocumentFamily, tuple[float, int, int]] = {}
    any_marker_matched = False
    for family, markers in FAMILY_MARKERS.items():
        matched = [(marker, weight) for marker, weight in markers if marker in normalized]
        any_marker_matched = any_marker_matched or bool(matched)
        penalty = 0.25 * sum(
            marker in normalized for marker in FAMILY_NEGATIVE_MARKERS.get(family, ())
        )
        weight = max(0.0, sum(item[1] for item in matched) - penalty)
        distinctive = sum(item[0] in DISTINCTIVE_MARKERS[family] for item in matched)
        evidence[family] = (weight, len(matched), distinctive)

    ranked = sorted(evidence.items(), key=lambda item: item[1], reverse=True)
    family, (weight, marker_count, distinctive_count) = ranked[0]
    runner_up_weight = ranked[1][1][0]
    if weight == 0:
        reason = "insufficient_distinctive_evidence" if any_marker_matched else "no_known_family_evidence"
        return ClassificationDecision(
            DocumentFamily.UNKNOWN,
            settings.classification_known_threshold,
            reason,
        )

    # One weak/generic phrase is not enough to name a family.  Competing
    # families with similar evidence also route to review instead of forcing a
    # confident answer.
    has_sufficient_evidence = distinctive_count >= 1 and (weight >= 1.0 or marker_count >= 2)
    ambiguous = runner_up_weight > 0 and weight - runner_up_weight < 0.5
    score = min(0.99, weight / 2.0)
    eligible = _has_family_promotion_evidence(family, text)
    if not eligible or not has_sufficient_evidence or score < settings.classification_known_threshold or ambiguous:
        # Generic-only matches are capped at the threshold and must never
        # become an automatic known-family assignment.
        uncertainty = min(settings.classification_known_threshold, max(0.01, score))
        if family == DocumentFamily.HOTEL and not eligible:
            reason = "hotel_confirmation_without_required_structured_stay_date_labels"
        elif family in {DocumentFamily.LEGAL_NOTICE, DocumentFamily.SHIPPING} and not eligible:
            reason = "family_schema_available_but_auto_classification_deferred"
        elif ambiguous:
            reason = "competing_family_evidence"
        else:
            reason = "insufficient_distinctive_evidence"
        return ClassificationDecision(DocumentFamily.UNKNOWN, round(uncertainty, 4), reason)
    return ClassificationDecision(family, round(score, 4))


def extract_unknown_fields(text: str) -> list[GenericFieldDecision]:
    fields = []
    for name, pattern in GENERIC_PATTERNS.items():
        match = pattern.search(text)
        value = match.group(1).strip() if match else None
        fields.append(GenericFieldDecision(
            name=name,
            value=value,
            confidence=0.90 if value else None,
            trust_state=TrustState.EXTRACTED if value else TrustState.NOT_FOUND,
        ))
    return fields


def _clean_extracted_value(value: str) -> str | None:
    # PDF text layers commonly place the next table column on the same text
    # line.  Keep the first column value rather than swallowing adjacent data.
    cleaned = re.split(r"[ \t]{3,}", value.strip(), maxsplit=1)[0].strip()
    if not cleaned:
        return None
    # Reject a captured nested label such as ``GST : 9.00`` when extracting
    # ``Total Amount``.  This was the source of the corpus's "GST :" error.
    if re.match(r"^[A-Za-z][A-Za-z /&().-]{0,30}\s*:", cleaned):
        return None
    # Some travel exports repeat the same reference on the same line. Keep
    # one value only when every comma-separated token is identical.
    repeated = [item.strip() for item in cleaned.split(",")]
    if len(repeated) > 1 and repeated[0] and len(set(repeated)) == 1:
        return repeated[0]
    return cleaned


_OCR_SEPARATED_VALUE_LABELS = {
    "service connection number",
    "servie connection number",
    "name of customer(billed to)",
    "name",
}
_OCR_HEADING_WORDS = {
    "address", "amount", "bill", "billing", "customer", "date", "description",
    "details", "email", "gst", "gstin", "invoice", "name", "nationality",
    "phase", "phone", "room", "tariff", "tax", "total",
}


def _is_plausible_separated_ocr_value(label: str, value: str) -> bool:
    """Validate values found several OCR blocks after a standalone label.

    PaddleOCR emits table cells as individual lines in reading order.  We only
    use the wider look-ahead for reviewed labels and require a value shape that
    is specific enough to avoid turning a neighbouring table heading into a
    field value.
    """
    normalized_label = label.casefold()
    candidate = value.strip().strip(":")
    if not candidate or ":" in candidate or len(candidate) > 100:
        return False
    if re.fullmatch(r"(?:id|passport)[ ._-]*(?:no|number)\.?", candidate, re.I):
        return False
    known_labels = {
        schema_label.casefold()
        for schema in PREDEFINED_SCHEMAS.values()
        for _, labels in schema.values()
        for schema_label in labels
    }
    if candidate.casefold() in known_labels:
        return False
    words = {word.casefold() for word in re.findall(r"[A-Za-z]+", candidate)}
    if words and words <= _OCR_HEADING_WORDS:
        return False
    if normalized_label in {"service connection number", "servie connection number"}:
        return bool(
            re.fullmatch(r"[A-Z0-9][A-Z0-9 /-]{4,30}", candidate, re.I)
            and any(char.isdigit() for char in candidate)
        )
    # The two reviewed name labels contain names, not free-form prose or IDs.
    name_heading_tokens = {
        "card", "customer", "guest", "id", "member", "nationality", "no",
        "number", "passport", "room",
    }
    if words & name_heading_tokens:
        return False
    return bool(
        re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,79}", candidate)
        and len(candidate.split()) <= 8
    )


def _extract_label_value(text: str, labels: tuple[str, ...], inferred: bool = False) -> str | None:
    lines = text.splitlines()
    prefix = r"inferred[ \t]+" if inferred else ""
    for label in sorted(labels, key=len, reverse=True):
        pattern = re.compile(
            rf"^[ \t]*{prefix}{re.escape(label)}[ \t]*:[ \t]*(.*)$",
            re.I,
        )
        for index, line in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            value = _clean_extracted_value(match.group(1))
            if value:
                return value
            # Table exports often place the value on the next non-empty line.
            for following in lines[index + 1:index + 3]:
                value = _clean_extracted_value(following)
                if value:
                    return value

        # Live PaddleOCR sometimes separates a table label and its value by
        # several intervening cells.  Use a bounded look-ahead only for the
        # reviewed labels whose value shapes can be validated conservatively.
        if not inferred and label.casefold() in _OCR_SEPARATED_VALUE_LABELS:
            standalone_label = re.compile(
                rf"^[ \t]*{re.escape(label)}[ \t]*:?\s*$",
                re.I,
            )
            for index, line in enumerate(lines):
                if not standalone_label.fullmatch(line):
                    continue
                for following in lines[index + 1:index + 7]:
                    # PaddleOCR may emit the delimiter with the value as its
                    # own block: ``Name`` followed by ``: Jane Doe``.
                    following = re.sub(r"^[ \t]*:[ \t]*", "", following, count=1)
                    value = _clean_extracted_value(following)
                    if value and _is_plausible_separated_ocr_value(label, value):
                        return value

        # PDF text layers often preserve columns as a long whitespace gap
        # instead of a colon. This remains line-start anchored so an alias
        # cannot fire on prose elsewhere in the row.
        column_labels = {
            "service connection number",
            "servie connection number",
            "name of customer(billed to)",
        }
        if label.casefold() in column_labels:
            column_pattern = re.compile(
                rf"^[ \t]*{prefix}{re.escape(label)}[ \t]{{2,}}(.+)$",
                re.I,
            )
            for line in lines:
                match = column_pattern.match(line)
                if match:
                    value = _clean_extracted_value(match.group(1))
                    if value:
                        return value

        # A labelled field may follow another column on the same text-layer
        # line. Require a word boundary before the complete alias and a colon
        # immediately after it. Short generic aliases such as ``Name`` are
        # excluded here so they cannot match inside ``Hotel Name``.
        if len(label) > 4 or label.casefold() == "pnr":
            embedded_pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){prefix}{re.escape(label)}\)?[ \t]*:[ \t]*(.+)$",
                re.I,
            )
            for line in lines:
                if not inferred and line.lstrip().casefold().startswith("inferred "):
                    continue
                match = embedded_pattern.search(line)
                if match:
                    value = _clean_extracted_value(match.group(1))
                    if value:
                        return value
    return None


def _extract_invoice_number_below_header(text: str) -> str | None:
    """Extract a bounded label-less invoice number directly below its header."""
    lines = text.splitlines()
    header = re.compile(r"^[ \t]*(?:tax|gst)[ \t]+invoice[ \t]*$", re.I)
    candidate = re.compile(r"^[A-Z0-9][A-Z0-9/-]{5,30}$", re.I)
    for index, line in enumerate(lines):
        if not header.match(line):
            continue
        # OCR reading order may place several header cells between TAX INVOICE
        # and the label-less identifier.  Keep this bounded and identifier-
        # shaped so totals, dates, and prose cannot be selected.
        for following in lines[index + 1:index + 9]:
            value = following.strip()
            if (
                value
                and candidate.fullmatch(value)
                and any(char.isdigit() for char in value)
                and any(char.isalpha() for char in value)
            ):
                return value
    return None


_TRAVEL_DATE_PATTERN = re.compile(
    r"\b(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|"
    r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?),?[ \t]+"
    r"(?P<day>\d{1,2})[ \t]+"
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?),?[ \t]+(?P<year>20\d{2})\b",
    re.I,
)
_TRAVEL_TIME_PATTERN = re.compile(
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?\b"
)
_TRAVEL_FLIGHT_PATTERN = re.compile(r"\b[A-Z]{2,3}[ \t]+\d{2,4}\b")
_TRAVEL_IATA_PATTERN = re.compile(r"\b[A-Z]{3}\b")
_MONTH_ABBREVIATIONS = {
    "jan": "Jan", "january": "Jan",
    "feb": "Feb", "february": "Feb",
    "mar": "Mar", "march": "Mar",
    "apr": "Apr", "april": "Apr",
    "may": "May",
    "jun": "Jun", "june": "Jun",
    "jul": "Jul", "july": "Jul",
    "aug": "Aug", "august": "Aug",
    "sep": "Sep", "september": "Sep",
    "oct": "Oct", "october": "Oct",
    "nov": "Nov", "november": "Nov",
    "dec": "Dec", "december": "Dec",
}


def _extract_label_less_travel_date(text: str) -> str | None:
    """Select one strongly structured, otherwise-unlabelled travel date.

    This is deliberately a fallback, not a general date extractor. A candidate
    must share a line with a time, a weekday, and a flight/airport code. If two
    distinct dates qualify, the result is ambiguous and remains ``not_found``.
    """
    candidates: set[str] = set()
    for line in text.splitlines():
        if not _TRAVEL_TIME_PATTERN.search(line):
            continue
        if not (
            _TRAVEL_FLIGHT_PATTERN.search(line)
            or _TRAVEL_IATA_PATTERN.search(line)
        ):
            continue
        for match in _TRAVEL_DATE_PATTERN.finditer(line):
            day = int(match.group("day"))
            if not 1 <= day <= 31:
                continue
            month = _MONTH_ABBREVIATIONS[match.group("month").casefold()]
            normalized = f"{day:02d} {month} {match.group('year')}"
            try:
                datetime.strptime(normalized, "%d %b %Y")
            except ValueError:
                continue
            candidates.add(normalized)
    return next(iter(candidates)) if len(candidates) == 1 else None


def extract_predefined_fields(family: DocumentFamily, text: str) -> list[GenericFieldDecision]:
    schema = PREDEFINED_SCHEMAS.get(family, {})
    fields = []
    for name, (criticality, labels) in schema.items():
        value = _extract_label_value(text, labels)
        if family == DocumentFamily.INVOICE_RECEIPT and name == "invoice_number" and not value:
            value = _extract_invoice_number_below_header(text)
        inferred_value = _extract_label_value(text, labels, inferred=True) if not value else None
        value = value or inferred_value
        fallback_value = None
        if family == DocumentFamily.TRAVEL and name == "departure_date" and not value:
            fallback_value = _extract_label_less_travel_date(text)
            value = fallback_value
        fields.append(GenericFieldDecision(
            name=name,
            value=value,
            confidence=0.75 if fallback_value else 0.90 if value else None,
            trust_state=(
                TrustState.INFERRED if inferred_value or fallback_value
                else TrustState.EXTRACTED if value
                else TrustState.NOT_FOUND
            ),
            criticality=criticality, schema_version=SCHEMA_VERSION,
        ))
    return fields
