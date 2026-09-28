from __future__ import annotations

import re
from dataclasses import dataclass

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
        "consumer_account_number": ("critical", ("Consumer Number", "Account Number")),
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
        "customer_name": ("standard", ("Customer Name", "Bill To")),
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
        "guest_name": ("critical", ("Guest", "Guest Name", "Client")),
        "property_name": ("critical", ("Hotel", "Property", "Property Name")),
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
        confidence = settings.classification_known_threshold if any_marker_matched else 1.0
        reason = "insufficient_distinctive_evidence" if any_marker_matched else "no_known_family_evidence"
        return ClassificationDecision(DocumentFamily.UNKNOWN, confidence, reason)

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
    return cleaned


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
    return None


def extract_predefined_fields(family: DocumentFamily, text: str) -> list[GenericFieldDecision]:
    schema = PREDEFINED_SCHEMAS.get(family, {})
    fields = []
    for name, (criticality, labels) in schema.items():
        value = _extract_label_value(text, labels)
        inferred_value = _extract_label_value(text, labels, inferred=True) if not value else None
        value = value or inferred_value
        fields.append(GenericFieldDecision(
            name=name, value=value, confidence=0.90 if value else None,
            trust_state=(
                TrustState.INFERRED if inferred_value
                else TrustState.EXTRACTED if value
                else TrustState.NOT_FOUND
            ),
            criticality=criticality, schema_version=SCHEMA_VERSION,
        ))
    return fields
