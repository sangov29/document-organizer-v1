from datetime import datetime
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
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
