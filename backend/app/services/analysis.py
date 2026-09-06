from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.models.enums import DocumentFamily, TrustState


PROVIDER = "builtin-rules"
MODEL_VERSION = "keyword-v1"
METHOD = "keyword_rules"

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
