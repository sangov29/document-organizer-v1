import hashlib
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditEvent, ClassificationResult, Document, ExtractedField, OCRArtifact,
    Page, ProcessingJob, Provenance, User,
)
from app.models.enums import AuditEventType, ProcessingStatus
from app.schemas.documents import (
    BulkUploadItemResponse, BulkUploadResponse, ClassificationResponse,
    DocumentAnalysisResponse, DocumentOCRResponse, DocumentResponse,
    ExtractedFieldResponse, OCRPageResponse, ResultProvenanceResponse,
)
from app.services.storage import storage
from app.workers.celery_app import bootstrap_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png"}


def doc_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc.id), original_filename=doc.original_filename, mime_type=doc.mime_type,
        size_bytes=doc.size_bytes, sha256=doc.sha256, status=doc.status.value,
        duplicate_of_document_id=(str(doc.duplicate_of_document_id) if doc.duplicate_of_document_id else None),
        uploaded_at=doc.uploaded_at,
    )


def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Supported formats are PDF, JPG and PNG")
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds configured upload limit")
    return data, hashlib.sha256(data).hexdigest()


def _persist_upload(
    file: UploadFile,
    data: bytes,
    digest: str,
    db: Session,
    user: User,
    duplicate_action: Literal["reject", "keep"] = "reject",
) -> Document:
    existing = db.scalar(
        select(Document).where(
            Document.user_id == user.id,
            Document.sha256 == digest,
            Document.duplicate_of_document_id.is_(None),
        )
    )
    if existing and duplicate_action == "reject":
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate_document", "existing_document_id": str(existing.id)},
        )

    doc_id = uuid.uuid4()
    object_key = f"users/{user.id}/documents/{doc_id}/source"
    storage.put_immutable(object_key, data, file.content_type or "application/octet-stream")
    doc = Document(
        id=doc_id, user_id=user.id, original_filename=file.filename or "upload",
        mime_type=file.content_type, object_key=object_key, sha256=digest,
        size_bytes=len(data), status=ProcessingStatus.QUEUED,
        duplicate_of_document_id=(existing.id if existing else None),
    )
    db.add(doc)
    db.flush()
    correlation_id = uuid.uuid4().hex
    db.add(ProcessingJob(
        document_id=doc.id, stage="ingestion", status=ProcessingStatus.QUEUED,
        correlation_id=correlation_id,
    ))
    db.add(AuditEvent(
        user_id=user.id, event_type=AuditEventType.UPLOAD,
        target_type="document", target_id=str(doc.id),
        metadata_json={"mime_type": file.content_type, "size_bytes": len(data)},
    ))
    if existing:
        db.add(AuditEvent(
            user_id=user.id, event_type=AuditEventType.DUPLICATE_OVERRIDE,
            target_type="document", target_id=str(doc.id),
            metadata_json={
                "action": "keep",
                "existing_document_id": str(existing.id),
                "sha256": digest,
            },
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(object_key)
        raise HTTPException(status_code=409, detail={"code": "duplicate_document"})
    except Exception:
        db.rollback()
        storage.delete(object_key)
        raise

    try:
        bootstrap_pipeline.delay(str(doc.id))
    except Exception as exc:
        # The source/document are already durably committed. Record queue
        # handoff failure explicitly so this document does not masquerade as
        # successfully queued, while allowing bulk siblings to continue.
        doc.status = ProcessingStatus.FAILED
        job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == doc.id, ProcessingJob.stage == "ingestion")
            .order_by(ProcessingJob.created_at.desc())
        )
        if job:
            job.status = ProcessingStatus.FAILED
            job.error_code = "QueueHandoffError"
        db.commit()
        raise RuntimeError("Processing queue handoff failed") from exc
    return doc


@router.post("", response_model=DocumentResponse, status_code=202)
def upload_document(
    file: UploadFile = File(...),
    duplicate_action: Literal["reject", "keep"] = Form("reject"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data, digest = _read_upload(file)
    return doc_response(_persist_upload(file, data, digest, db, user, duplicate_action))


@router.post("/bulk", response_model=BulkUploadResponse)
def bulk_upload_documents(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items: list[BulkUploadItemResponse] = []
    queued_count = 0

    for file in files:
        filename = file.filename or "upload"
        try:
            data, digest = _read_upload(file)
            doc = _persist_upload(file, data, digest, db, user)
            items.append(BulkUploadItemResponse(filename=filename, outcome="queued", document=doc_response(doc)))
            queued_count += 1
        except HTTPException as exc:
            db.rollback()
            detail = exc.detail
            if exc.status_code == 409 and isinstance(detail, dict) and detail.get("code") == "duplicate_document":
                items.append(BulkUploadItemResponse(
                    filename=filename, outcome="duplicate",
                    existing_document_id=detail.get("existing_document_id"),
                    error_code="duplicate_document",
                    message="Exact duplicate already exists",
                ))
            else:
                items.append(BulkUploadItemResponse(
                    filename=filename, outcome="rejected", error_code=f"http_{exc.status_code}",
                    message=str(detail),
                ))
        except Exception as exc:
            db.rollback()
            items.append(BulkUploadItemResponse(
                filename=filename, outcome="failed", error_code=exc.__class__.__name__,
                message="Upload could not be queued",
            ))

    return BulkUploadResponse(items=items, queued_count=queued_count, failed_count=len(items) - queued_count)


@router.get("", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    docs = db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.uploaded_at.desc())).all()
    return [doc_response(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if not document:
        # Use the same response for nonexistent and foreign-owned identifiers so
        # the endpoint cannot be used to enumerate another user's documents.
        raise HTTPException(status_code=404, detail="Document not found")
    return doc_response(document)


@router.get("/{document_id}/ocr", response_model=DocumentOCRResponse)
def get_document_ocr(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    rows = db.execute(
        select(Page, OCRArtifact)
        .join(OCRArtifact, OCRArtifact.page_id == Page.id)
        .where(Page.document_id == document.id)
        .order_by(Page.page_number)
    ).all()
    page_count = db.scalar(select(func.count(Page.id)).where(Page.document_id == document.id)) or 0
    if not rows or len(rows) < page_count:
        raise HTTPException(status_code=202, detail="OCR processing is not complete")
    return DocumentOCRResponse(
        document_id=str(document.id),
        pages=[
            OCRPageResponse(
                page_id=str(page.id), page_number=page.page_number,
                text=artifact.text, confidence=artifact.confidence,
                blocks=artifact.blocks, provider=artifact.provider,
                model_version=artifact.model_version, method=artifact.method,
                language=artifact.language, processed_at=artifact.created_at,
            )
            for page, artifact in rows
        ],
    )


def _provenance_response(provenance: Provenance) -> ResultProvenanceResponse:
    return ResultProvenanceResponse(
        source_document_id=str(provenance.source_document_id),
        source_page_id=str(provenance.source_page_id) if provenance.source_page_id else None,
        visual_region_id=str(provenance.visual_region_id) if provenance.visual_region_id else None,
        provider=provenance.provider, model_version=provenance.model_version,
        method=provenance.method, confidence=provenance.confidence,
        processed_at=provenance.processed_at,
    )


@router.get("/{document_id}/analysis", response_model=DocumentAnalysisResponse)
def get_document_analysis(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    classification = db.scalar(
        select(ClassificationResult).where(
            ClassificationResult.document_id == document.id,
            ClassificationResult.is_active.is_(True),
        ).order_by(ClassificationResult.processed_at.desc())
    )
    if not classification:
        raise HTTPException(status_code=202, detail="Classification is not complete")
    classification_provenance = db.scalar(
        select(Provenance).where(Provenance.classification_result_id == classification.id)
    )
    if not classification_provenance:
        raise HTTPException(status_code=500, detail="Classification provenance is missing")

    fields = db.scalars(
        select(ExtractedField).where(
            ExtractedField.document_id == document.id,
            ExtractedField.is_active.is_(True),
        ).order_by(ExtractedField.field_name)
    ).all()
    field_responses = []
    for field in fields:
        provenance = db.scalar(
            select(Provenance).where(Provenance.extracted_field_id == field.id)
        )
        if not provenance:
            raise HTTPException(status_code=500, detail="Field provenance is missing")
        field_responses.append(ExtractedFieldResponse(
            field_name=field.field_name, value=field.value,
            confidence=field.confidence, trust_state=field.trust_state.value,
            criticality=field.criticality, schema_version=field.schema_version,
            provenance=_provenance_response(provenance),
        ))
    return DocumentAnalysisResponse(
        document_id=str(document.id),
        classification=ClassificationResponse(
            family=classification.family.value,
            confidence=classification.confidence,
            provider=classification.provider,
            model_version=classification.model_version,
            method=classification.method,
            processed_at=classification.processed_at,
            configured_threshold=settings.classification_known_threshold,
            provenance=_provenance_response(classification_provenance),
        ),
        fields=field_responses,
    )
