import base64
import hashlib
import uuid
from io import BytesIO
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditEvent, ClassificationResult, Correction, Document, ExtractedField,
    OCRArtifact, Page, PreprocessingResult, ProcessingJob, Provenance,
    SensitivityTag, User, VisualRegion,
)
from app.models.enums import AuditEventType, ProcessingStatus, TrustState
from app.schemas.documents import (
    BulkUploadItemResponse, BulkUploadResponse, ClassificationResponse,
    DocumentAnalysisResponse, DocumentOCRResponse, DocumentResponse,
    ExtractedFieldResponse, FieldReviewRequest, OCRPageResponse, ResultProvenanceResponse,
    SensitiveRegionResponse, SensitiveRevealResponse,
)
from app.services.sensitivity import mask_ocr_blocks, mask_ocr_text, mask_sensitive_value
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
                text=mask_ocr_text(artifact.text), confidence=artifact.confidence,
                blocks=mask_ocr_blocks(artifact.blocks), provider=artifact.provider,
                model_version=artifact.model_version, method=artifact.method,
                language=artifact.language, processed_at=artifact.created_at,
            )
            for page, artifact in rows
        ],
    )


def _provenance_response(provenance: Provenance) -> ResultProvenanceResponse:
    return ResultProvenanceResponse(
        id=str(provenance.id),
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
        sensitivity = db.scalar(
            select(SensitivityTag).where(SensitivityTag.extracted_field_id == field.id)
        )
        is_sensitive = sensitivity is not None
        field_responses.append(ExtractedFieldResponse(
            id=str(field.id),
            field_name=field.field_name,
            value=mask_sensitive_value(field.value) if is_sensitive else field.value,
            confidence=field.confidence, trust_state=field.trust_state.value,
            criticality=field.criticality, schema_version=field.schema_version,
            provenance=_provenance_response(provenance),
            corrections=[{
                "id": str(c.id),
                "prior_value": mask_sensitive_value(c.prior_value) if is_sensitive else c.prior_value,
                "corrected_value": mask_sensitive_value(c.corrected_value) if is_sensitive else c.corrected_value,
                "user_id": str(c.user_id),
                "prior_provenance_id": str(c.prior_provenance_id) if c.prior_provenance_id else None,
                "created_at": c.created_at,
            } for c in db.scalars(select(Correction).where(Correction.extracted_field_id == field.id).order_by(Correction.created_at)).all()],
            sensitive=is_sensitive,
            sensitivity_type=sensitivity.sensitivity_type if sensitivity else None,
            masked=is_sensitive and field.value is not None,
        ))
    sensitive_regions = [
        SensitiveRegionResponse(
            id=str(region.id), region_type=region.region_type,
            sensitivity_type=tag.sensitivity_type, bbox=region.bbox,
        )
        for region, tag in db.execute(
            select(VisualRegion, SensitivityTag)
            .join(SensitivityTag, SensitivityTag.visual_region_id == VisualRegion.id)
            .join(Page, Page.id == VisualRegion.page_id)
            .where(Page.document_id == document.id)
            .order_by(VisualRegion.id)
        ).all()
    ]
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
        sensitive_regions=sensitive_regions,
    )


@router.post("/{document_id}/fields/{field_id}/review", response_model=DocumentAnalysisResponse)
def review_field(document_id: uuid.UUID, field_id: uuid.UUID, request: FieldReviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    field = db.scalar(select(ExtractedField).where(ExtractedField.id == field_id, ExtractedField.document_id == document_id, ExtractedField.is_active.is_(True)))
    if not document or not field:
        raise HTTPException(status_code=404, detail="Field not found")
    provenance = db.scalar(select(Provenance).where(Provenance.extracted_field_id == field.id))
    if request.action == "correct":
        value = (request.value or "").strip()
        if not value:
            raise HTTPException(status_code=422, detail="Corrected value is required")
        correction = Correction(extracted_field_id=field.id, user_id=user.id, prior_value=field.value, corrected_value=value, prior_provenance_id=provenance.id if provenance else None)
        db.add(correction); field.value = value; field.confidence = None; field.trust_state = TrustState.CORRECTED
        event = AuditEventType.CORRECTION
    else:
        field.trust_state = TrustState.CONFIRMED; event = AuditEventType.CONFIRMATION
    db.add(AuditEvent(user_id=user.id, event_type=event, target_type="extracted_field", target_id=str(field.id), metadata_json={"action": request.action, "field_name": field.field_name}))
    db.commit()
    return get_document_analysis(document_id, db, user)


@router.post("/{document_id}/fields/{field_id}/reveal", response_model=SensitiveRevealResponse)
def reveal_sensitive_field(
    document_id: uuid.UUID,
    field_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    field = db.scalar(
        select(ExtractedField)
        .join(Document, Document.id == ExtractedField.document_id)
        .where(
            ExtractedField.id == field_id,
            ExtractedField.document_id == document_id,
            Document.user_id == user.id,
            ExtractedField.is_active.is_(True),
        )
    )
    sensitivity = db.scalar(
        select(SensitivityTag).where(SensitivityTag.extracted_field_id == field.id)
    ) if field else None
    if not field or not sensitivity:
        raise HTTPException(status_code=404, detail="Sensitive field not found")
    db.add(AuditEvent(
        user_id=user.id, event_type=AuditEventType.SENSITIVE_REVEAL,
        target_type="extracted_field", target_id=str(field.id),
        metadata_json={
            "action": "reveal", "subject_type": "extracted_field",
            "field_name": field.field_name,
            "sensitivity_type": sensitivity.sensitivity_type,
        },
    ))
    db.commit()
    response.headers["Cache-Control"] = "no-store, private"
    return SensitiveRevealResponse(
        subject_type="extracted_field", subject_id=str(field.id),
        sensitivity_type=sensitivity.sensitivity_type,
        revealed_value=field.value,
    )


@router.post("/{document_id}/regions/{region_id}/reveal", response_model=SensitiveRevealResponse)
def reveal_sensitive_region(
    document_id: uuid.UUID,
    region_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.execute(
        select(VisualRegion, SensitivityTag, PreprocessingResult)
        .join(Page, Page.id == VisualRegion.page_id)
        .join(Document, Document.id == Page.document_id)
        .join(SensitivityTag, SensitivityTag.visual_region_id == VisualRegion.id)
        .join(PreprocessingResult, PreprocessingResult.page_id == Page.id)
        .where(
            VisualRegion.id == region_id,
            Page.document_id == document_id,
            Document.user_id == user.id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Sensitive region not found")
    region, sensitivity, preprocessing = row
    source = Image.open(BytesIO(storage.get_bytes(preprocessing.normalized_object_key))).convert("RGB")
    box = region.bbox
    padding = 8
    left = max(0, box["x"] - padding)
    top = max(0, box["y"] - padding)
    right = min(source.width, box["x"] + box["width"] + padding)
    bottom = min(source.height, box["y"] + box["height"] + padding)
    output = BytesIO()
    source.crop((left, top, right, bottom)).save(output, "PNG")
    db.add(AuditEvent(
        user_id=user.id, event_type=AuditEventType.SENSITIVE_REVEAL,
        target_type="visual_region", target_id=str(region.id),
        metadata_json={
            "action": "reveal", "subject_type": "visual_region",
            "region_type": region.region_type,
            "sensitivity_type": sensitivity.sensitivity_type,
        },
    ))
    db.commit()
    response.headers["Cache-Control"] = "no-store, private"
    return SensitiveRevealResponse(
        subject_type="visual_region", subject_id=str(region.id),
        sensitivity_type=sensitivity.sensitivity_type,
        content_base64=base64.b64encode(output.getvalue()).decode("ascii"),
        media_type="image/png",
    )
