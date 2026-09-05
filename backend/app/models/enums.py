import enum


class DocumentFamily(str, enum.Enum):
    IDENTITY = "identity"
    UTILITY = "utility"
    BANKING = "banking"
    EDUCATIONAL = "educational"
    EMPLOYMENT = "employment"
    INVOICE_RECEIPT = "invoice_receipt"
    TRAVEL = "travel"
    UNKNOWN = "unknown"


class TrustState(str, enum.Enum):
    EXTRACTED = "extracted"
    UNCERTAIN = "uncertain"
    NOT_FOUND = "not_found"
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


class SensitivitySubjectType(str, enum.Enum):
    EXTRACTED_FIELD = "extracted_field"
    VISUAL_REGION = "visual_region"


class ProcessingStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"


class AuditEventType(str, enum.Enum):
    UPLOAD = "upload"
    CORRECTION = "correction"
    CONFIRMATION = "confirmation"
    SENSITIVE_REVEAL = "sensitive_reveal"
    DUPLICATE_OVERRIDE = "duplicate_override"
    DELETION = "deletion"
    AUTH_SECURITY = "auth_security"
