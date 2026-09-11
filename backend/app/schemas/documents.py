from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    duplicate_of_document_id: str | None = None
    status: str
    uploaded_at: datetime


class OrganizedDocumentResponse(DocumentResponse):
    family: str
    organization_label: str


class DocumentSearchResponse(BaseModel):
    items: list[OrganizedDocumentResponse]
    total: int
    page: int
    page_size: int


class AuditEventResponse(BaseModel):
    id: str
    event_type: str
    target_type: str
    target_id: str | None
    metadata: dict
    created_at: datetime


class BulkUploadItemResponse(BaseModel):
    filename: str
    outcome: str
    document: DocumentResponse | None = None
    existing_document_id: str | None = None
    error_code: str | None = None
    message: str | None = None


class BulkUploadResponse(BaseModel):
    items: list[BulkUploadItemResponse]
    queued_count: int
    failed_count: int


class BatchExportRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=100)


class OCRWordResponse(BaseModel):
    text: str
    confidence: float
    bbox: dict[str, int]


class OCRPageResponse(BaseModel):
    page_id: str
    page_number: int
    text: str
    confidence: float | None
    blocks: list[OCRWordResponse]
    provider: str
    model_version: str
    method: str
    language: str
    processed_at: datetime


class DocumentOCRResponse(BaseModel):
    document_id: str
    pages: list[OCRPageResponse]


class ResultProvenanceResponse(BaseModel):
    id: str
    source_document_id: str
    source_page_id: str | None
    visual_region_id: str | None
    provider: str
    model_version: str
    method: str
    confidence: float | None
    processed_at: datetime


class ClassificationResponse(BaseModel):
    family: str
    confidence: float
    provider: str
    model_version: str
    method: str
    processed_at: datetime
    configured_threshold: float
    review_required: bool
    reviewed_at: datetime | None = None
    provenance: ResultProvenanceResponse


class ClassificationReviewRequest(BaseModel):
    action: Literal["confirm"]


class ExtractedFieldResponse(BaseModel):
    id: str
    field_name: str
    value: str | None
    confidence: float | None
    trust_state: str
    criticality: str
    schema_version: str | None
    provenance: ResultProvenanceResponse
    corrections: list[dict] = Field(default_factory=list)
    sensitive: bool = False
    sensitivity_type: str | None = None
    masked: bool = False


class SensitiveRegionResponse(BaseModel):
    id: str
    region_type: str
    sensitivity_type: str
    bbox: dict[str, int]
    concealed: bool = True


class SensitiveRevealResponse(BaseModel):
    subject_type: Literal["extracted_field", "visual_region"]
    subject_id: str
    sensitivity_type: str
    revealed_value: str | None = None
    content_base64: str | None = None
    media_type: str | None = None


class FieldReviewRequest(BaseModel):
    action: Literal["confirm", "correct"]
    value: str | None = None


class DocumentAnalysisResponse(BaseModel):
    document_id: str
    classification: ClassificationResponse
    fields: list[ExtractedFieldResponse]
    sensitive_regions: list[SensitiveRegionResponse] = Field(default_factory=list)
