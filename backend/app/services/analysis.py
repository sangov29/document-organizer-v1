from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.models.enums import DocumentFamily, TrustState


PROVIDER = "builtin-rules"
MODEL_VERSION = "keyword-v1"
METHOD = "keyword_rules"
SCHEMA_VERSION = "schema-v0.1"

FAMILY_MARKERS: dict[DocumentFamily, tuple[str, ...]] = {
    DocumentFamily.IDENTITY: ("PASSPORT", "IDENTITY", "DATE OF BIRTH"),
    DocumentFamily.UTILITY: ("UTILITY", "ELECTRICITY", "AMOUNT DUE"),
    DocumentFamily.BANKING: ("BANK STATEMENT", "IBAN", "ACCOUNT STATEMENT"),
    DocumentFamily.EDUCATIONAL: ("TRANSCRIPT", "UNIVERSITY", "CERTIFICATE"),
    DocumentFamily.EMPLOYMENT: ("PAYSLIP", "EMPLOYMENT", "SALARY"),
    DocumentFamily.INVOICE_RECEIPT: ("INVOICE", "RECEIPT", "TOTAL"),
    DocumentFamily.TRAVEL: ("BOARDING PASS", "FLIGHT", "ITINERARY"),
}

GENERIC_PATTERNS = {
    "generic_name": re.compile(r"^\s*name\s*:\s*(.+?)\s*$", re.I | re.M),
    "generic_date": re.compile(r"^\s*date\s*:\s*(.+?)\s*$", re.I | re.M),
    "generic_amount": re.compile(r"^\s*amount\s*:\s*(.+?)\s*$", re.I | re.M),
    "generic_address": re.compile(r"^\s*address\s*:\s*(.+?)\s*$", re.I | re.M),
}

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
        "invoice_date": ("critical", ("Invoice Date", "Receipt Date", "Date")),
        "customer_name": ("standard", ("Customer Name", "Bill To")),
        "subtotal": ("standard", ("Subtotal", "Sub Total")),
        "tax_amount": ("standard", ("Tax Amount", "Tax", "GST", "VAT")),
        "total_amount": ("critical", ("Total Amount", "Grand Total", "Total")),
        "currency": ("standard", ("Currency",)),
        "payment_due_date": ("standard", ("Payment Due Date", "Due Date")),
    },
}


@dataclass(frozen=True)
class ClassificationDecision:
    family: DocumentFamily
    confidence: float
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
    scores = {
        family: sum(marker in normalized for marker in markers) / len(markers)
        for family, markers in FAMILY_MARKERS.items()
    }
    family, score = max(scores.items(), key=lambda item: item[1])
    if score < settings.classification_known_threshold:
        return ClassificationDecision(DocumentFamily.UNKNOWN, round(1.0 - score, 4))
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


def extract_predefined_fields(family: DocumentFamily, text: str) -> list[GenericFieldDecision]:
    schema = PREDEFINED_SCHEMAS.get(family, {})
    fields = []
    for name, (criticality, labels) in schema.items():
        alternatives = "|".join(re.escape(label) for label in labels)
        # Keep the value boundary line-local. ``\s`` also includes newlines;
        # explicit horizontal whitespace plus a greedy non-newline capture
        # preserves the final non-space character.
        pattern = re.compile(
            rf"^[ \t]*(?:{alternatives})[ \t]*:[ \t]*([^\r\n]*\S)[ \t]*$",
            re.I | re.M,
        )
        inferred_pattern = re.compile(
            rf"^[ \t]*inferred[ \t]+(?:{alternatives})[ \t]*:[ \t]*([^\r\n]*\S)[ \t]*$",
            re.I | re.M,
        )
        match = pattern.search(text)
        inferred_match = inferred_pattern.search(text) if not match else None
        match = match or inferred_match
        value = match.group(1).strip() if match else None
        fields.append(GenericFieldDecision(
            name=name, value=value, confidence=0.90 if value else None,
            trust_state=(
                TrustState.INFERRED if inferred_match
                else TrustState.EXTRACTED if value
                else TrustState.NOT_FOUND
            ),
            criticality=criticality, schema_version=SCHEMA_VERSION,
        ))
    return fields
