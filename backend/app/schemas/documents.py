from datetime import datetime
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    duplicate_of_document_id: str | None = None
    status: str
    uploaded_at: datetime


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
    provenance: ResultProvenanceResponse


class ExtractedFieldResponse(BaseModel):
    field_name: str
    value: str | None
    confidence: float | None
    trust_state: str
    criticality: str
    provenance: ResultProvenanceResponse


class DocumentAnalysisResponse(BaseModel):
    document_id: str
    classification: ClassificationResponse
    fields: list[ExtractedFieldResponse]
