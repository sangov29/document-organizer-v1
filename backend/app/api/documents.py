import base64
import csv
import hashlib
import io
import json
import uuid
from io import BytesIO
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw
from sqlalchemy import delete, exists, func, or_, select
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
    AuditEventResponse, AuditLogResponse, BatchExportRequest, BulkUploadItemResponse, BulkUploadResponse, ClassificationResponse,
    ClassificationReviewRequest,
    DocumentAnalysisResponse, DocumentOCRResponse, DocumentResponse, DocumentSearchResponse,
    ExtractedFieldResponse, FieldReviewRequest, OCRPageResponse, ResultProvenanceResponse,
    OrganizedDocumentResponse, SensitiveRegionResponse, SensitiveRevealResponse,
)
from app.services.sensitivity import mask_ocr_blocks, mask_ocr_text, mask_sensitive_value
from app.services.storage import storage
from app.workers.celery_app import bootstrap_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png"}
EXPORT_SCHEMA_VERSION = "export-v0.1"
SENSITIVE_EXPORT_POLICY = "masked_no_bulk_reveal_v1"
AUDIT_SCHEMA_VERSION = "audit-export-v0.1"


def doc_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc.id), original_filename=doc.original_filename, mime_type=doc.mime_type,
        size_bytes=doc.size_bytes, sha256=doc.sha256, status=doc.status.value,
        duplicate_of_document_id=(str(doc.duplicate_of_document_id) if doc.duplicate_of_document_id else None),
        uploaded_at=doc.uploaded_at,
    )


def audit_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=str(event.id), event_type=event.event_type.value,
        target_type=event.target_type, target_id=event.target_id,
        metadata=event.metadata_json, created_at=event.created_at,
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


@router.get("/search", response_model=DocumentSearchResponse)
def search_documents(
    q: str | None = Query(None, max_length=200),
    family: str | None = Query(None, max_length=64),
    field_value: str | None = Query(None, max_length=200),
    uploaded_from: datetime | None = None,
    uploaded_to: datetime | None = None,
    sort: Literal["newest", "oldest"] = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    active_classification = exists().where(
        ClassificationResult.document_id == Document.id,
        ClassificationResult.is_active.is_(True),
        ClassificationResult.family == family,
    ) if family else None
    searchable_field = exists().where(
        ExtractedField.document_id == Document.id,
        ExtractedField.is_active.is_(True),
        ExtractedField.value.ilike(f"%{field_value}%"),
        ~exists().where(SensitivityTag.extracted_field_id == ExtractedField.id),
    ) if field_value else None
    statement = select(Document).where(Document.user_id == user.id)
    if q:
        statement = statement.where(Document.original_filename.ilike(f"%{q}%"))
    if active_classification is not None:
        statement = statement.where(active_classification)
    if searchable_field is not None:
        statement = statement.where(searchable_field)
    if uploaded_from:
        statement = statement.where(Document.uploaded_at >= uploaded_from)
    if uploaded_to:
        statement = statement.where(Document.uploaded_at <= uploaded_to)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    order = Document.uploaded_at.asc() if sort == "oldest" else Document.uploaded_at.desc()
    documents = db.scalars(statement.order_by(order, Document.id).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for document in documents:
        classification = db.scalar(select(ClassificationResult).where(
            ClassificationResult.document_id == document.id,
            ClassificationResult.is_active.is_(True),
        ).order_by(ClassificationResult.processed_at.desc()))
        family_value = classification.family.value if classification else "processing"
        items.append(OrganizedDocumentResponse(
            **doc_response(document).model_dump(), family=family_value,
            organization_label=("Unknown documents" if family_value == "unknown" else family_value.replace("_", " ").title()),
        ))
    return DocumentSearchResponse(items=items, total=total, page=page, page_size=page_size)


def _owner_document_audit(db: Session, user_id: uuid.UUID, limit: int) -> list[AuditEvent]:
    return list(db.scalars(
        select(AuditEvent).where(
            AuditEvent.user_id == user_id,
            AuditEvent.target_type.in_(("document", "extracted_field", "visual_region")),
        ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)
    ).all())


@router.get("/audit", response_model=AuditLogResponse)
def list_document_audit_events(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the owner's immutable document activity, including deletions."""
    events = _owner_document_audit(db, user.id, limit)
    return AuditLogResponse(
        schema_version=AUDIT_SCHEMA_VERSION,
        events=[audit_response(event) for event in events],
    )


@router.get("/audit/export.json")
def export_document_audit_events(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = AuditLogResponse(
        schema_version=AUDIT_SCHEMA_VERSION,
        events=[audit_response(event) for event in _owner_document_audit(db, user.id, 500)],
    ).model_dump(mode="json")
    return Response(
        content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=document-audit.json",
            "Cache-Control": "no-store, private",
        },
    )


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


@router.get("/{document_id}/audit", response_model=AuditLogResponse)
def get_document_audit_events(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    field_ids = [str(value) for value in db.scalars(
        select(ExtractedField.id).where(ExtractedField.document_id == document.id)
    ).all()]
    region_ids = [str(value) for value in db.scalars(
        select(VisualRegion.id).join(Page, Page.id == VisualRegion.page_id)
        .where(Page.document_id == document.id)
    ).all()]
    target_ids = [str(document.id), *field_ids, *region_ids]
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.user_id == user.id,
            AuditEvent.target_id.in_(target_ids),
        ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    ).all()
    return AuditLogResponse(
        schema_version=AUDIT_SCHEMA_VERSION,
        events=[audit_response(event) for event in events],
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently remove owner document data while retaining a minimal audit fact."""
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = db.scalars(select(Page).where(Page.document_id == document.id)).all()
    page_ids = [page.id for page in pages]
    normalized_keys = db.scalars(
        select(PreprocessingResult.normalized_object_key)
        .where(PreprocessingResult.page_id.in_(page_ids))
    ).all() if page_ids else []
    object_keys = [
        document.object_key,
        *(page.derived_object_key for page in pages if page.derived_object_key),
        *normalized_keys,
    ]
    try:
        storage.delete_many(object_keys)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Document storage cleanup could not be completed") from exc

    field_ids = db.scalars(
        select(ExtractedField.id).where(ExtractedField.document_id == document.id)
    ).all()
    if field_ids:
        db.execute(delete(Correction).where(Correction.extracted_field_id.in_(field_ids)))
    db.add(AuditEvent(
        user_id=user.id, event_type=AuditEventType.DELETION,
        target_type="document", target_id=str(document.id),
        metadata_json={"action": "permanent_delete", "object_count": len(set(object_keys))},
    ))
    db.delete(document)
    db.commit()
    return Response(status_code=204)


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


def _classification_review_required(classification: ClassificationResult) -> bool:
    return (
        classification.family.value == "unknown"
        and classification.confidence < 1.0
        and classification.reviewed_at is None
    )


def _sensitive_regions_for_document(
    db: Session, document_id: uuid.UUID, field_responses: list[ExtractedFieldResponse]
) -> list[SensitiveRegionResponse]:
    """Serialize direct region tags and field tags linked via provenance."""
    direct_rows = db.execute(
        select(VisualRegion, SensitivityTag)
        .join(SensitivityTag, SensitivityTag.visual_region_id == VisualRegion.id)
        .join(Page, Page.id == VisualRegion.page_id)
        .where(Page.document_id == document_id)
    ).all()
    field_rows = db.execute(
        select(VisualRegion, SensitivityTag)
        .join(Provenance, Provenance.visual_region_id == VisualRegion.id)
        .join(ExtractedField, ExtractedField.id == Provenance.extracted_field_id)
        .join(SensitivityTag, SensitivityTag.extracted_field_id == ExtractedField.id)
        .join(Page, Page.id == VisualRegion.page_id)
        .where(Page.document_id == document_id, ExtractedField.is_active.is_(True))
    ).all()

    serialized: dict[uuid.UUID, SensitiveRegionResponse] = {}
    for region, tag in [*direct_rows, *field_rows]:
        response = SensitiveRegionResponse(
            id=str(region.id), page_id=str(region.page_id), region_type=region.region_type,
            sensitivity_type=tag.sensitivity_type, bbox=region.bbox,
        )
        existing = serialized.get(region.id)
        if existing is not None and existing != response:
            raise HTTPException(status_code=500, detail="Sensitive region has conflicting tags")
        serialized[region.id] = response

    referenced_ids = {
        field.provenance.visual_region_id
        for field in field_responses
        if field.sensitive and field.provenance.visual_region_id is not None
    }
    missing_ids = referenced_ids - {str(region_id) for region_id in serialized}
    if missing_ids:
        raise HTTPException(status_code=500, detail="Sensitive field region is missing")
    return [serialized[key] for key in sorted(serialized, key=str)]


@router.get("/{document_id}/pages/{page_id}/preview")
def get_page_preview(
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return an owner-only normalized preview with sensitive pixels concealed."""
    row = db.execute(
        select(Page, PreprocessingResult)
        .join(Document, Document.id == Page.document_id)
        .join(PreprocessingResult, PreprocessingResult.page_id == Page.id)
        .where(Page.id == page_id, Page.document_id == document_id, Document.user_id == user.id)
    ).first()
    if not row:
        document = db.scalar(
            select(Document).where(Document.id == document_id, Document.user_id == user.id)
        )
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        raise HTTPException(status_code=202, detail="Page preview is not ready")
    page, preprocessing = row
    direct_regions = db.scalars(
        select(VisualRegion)
        .join(SensitivityTag, SensitivityTag.visual_region_id == VisualRegion.id)
        .where(VisualRegion.page_id == page.id)
    ).all()
    field_regions = db.scalars(
        select(VisualRegion)
        .join(Provenance, Provenance.visual_region_id == VisualRegion.id)
        .join(ExtractedField, ExtractedField.id == Provenance.extracted_field_id)
        .join(SensitivityTag, SensitivityTag.extracted_field_id == ExtractedField.id)
        .where(VisualRegion.page_id == page.id, ExtractedField.document_id == document_id)
    ).all()
    image = Image.open(BytesIO(storage.get_bytes(preprocessing.normalized_object_key))).convert("RGB")
    draw = ImageDraw.Draw(image)
    for region in {item.id: item for item in [*direct_regions, *field_regions]}.values():
        box = region.bbox
        left, top = max(0, box["x"]), max(0, box["y"])
        right = min(image.width, left + max(1, box["width"]))
        bottom = min(image.height, top + max(1, box["height"]))
        draw.rectangle((left, top, right, bottom), fill="#17231e", outline="#176b4d", width=3)
        draw.text((left + 6, top + 5), "CONCEALED", fill="white")
    output = BytesIO()
    image.save(output, "PNG")
    output.seek(0)
    return StreamingResponse(
        output, media_type="image/png",
        headers={"Cache-Control": "no-store, private", "Content-Disposition": "inline"},
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
    sensitive_regions = _sensitive_regions_for_document(db, document.id, field_responses)
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
            review_required=_classification_review_required(classification),
            reviewed_at=classification.reviewed_at,
            provenance=_provenance_response(classification_provenance),
        ),
        fields=field_responses,
        sensitive_regions=sensitive_regions,
    )


@router.post("/{document_id}/classification/review", response_model=DocumentAnalysisResponse)
def review_classification(
    document_id: uuid.UUID,
    request: ClassificationReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    classification = db.scalar(select(ClassificationResult).where(
        ClassificationResult.document_id == document_id,
        ClassificationResult.is_active.is_(True),
    ).order_by(ClassificationResult.processed_at.desc())) if document else None
    if not document or not classification:
        raise HTTPException(status_code=404, detail="Classification not found")
    classification.reviewed_at = datetime.now(timezone.utc)
    db.add(AuditEvent(
        user_id=user.id, event_type=AuditEventType.CONFIRMATION,
        target_type="classification_result", target_id=str(classification.id),
        metadata_json={"action": request.action, "family": classification.family.value},
    ))
    db.commit()
    return get_document_analysis(document_id, db, user)


def _export_payload(document: Document, analysis: DocumentAnalysisResponse) -> dict:
    return {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "sensitive_export_policy": SENSITIVE_EXPORT_POLICY,
        "document": doc_response(document).model_dump(mode="json"),
        "classification": analysis.classification.model_dump(mode="json"),
        "fields": [field.model_dump(mode="json") for field in analysis.fields],
    }


@router.get("/{document_id}/export.json")
def export_document_json(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    analysis = get_document_analysis(document_id, db, user)
    body = json.dumps(_export_payload(document, analysis), sort_keys=True, separators=(",", ":"))
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="document-{document_id}.json"',
            "Cache-Control": "no-store, private",
        },
    )


@router.post("/batch/export.csv")
def export_documents_csv(
    request: BatchExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        ids = list(dict.fromkeys(uuid.UUID(value) for value in request.document_ids))
    except ValueError:
        raise HTTPException(status_code=422, detail="Every document ID must be a UUID")
    documents = db.scalars(
        select(Document).where(Document.id.in_(ids), Document.user_id == user.id)
    ).all()
    by_id = {document.id: document for document in documents}
    if len(by_id) != len(ids):
        raise HTTPException(status_code=404, detail="Document not found")

    headers = [
        "export_schema_version", "sensitive_export_policy", "document_id",
        "original_filename", "family", "field_name", "value", "confidence",
        "trust_state", "criticality", "schema_version", "provider",
        "model_version", "method", "source_page_id", "visual_region_id",
        "sensitivity_type", "masked",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for document_id in ids:
        document = by_id[document_id]
        analysis = get_document_analysis(document_id, db, user)
        for field in analysis.fields:
            writer.writerow({
                "export_schema_version": EXPORT_SCHEMA_VERSION,
                "sensitive_export_policy": SENSITIVE_EXPORT_POLICY,
                "document_id": str(document.id),
                "original_filename": document.original_filename,
                "family": analysis.classification.family,
                "field_name": field.field_name,
                "value": field.value or "",
                "confidence": "" if field.confidence is None else field.confidence,
                "trust_state": field.trust_state,
                "criticality": field.criticality,
                "schema_version": field.schema_version or "",
                "provider": field.provenance.provider,
                "model_version": field.provenance.model_version,
                "method": field.provenance.method,
                "source_page_id": field.provenance.source_page_id or "",
                "visual_region_id": field.provenance.visual_region_id or "",
                "sensitivity_type": field.sensitivity_type or "",
                "masked": str(field.masked).lower(),
            })
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=documents-export.csv",
            "Cache-Control": "no-store, private",
        },
    )


@router.post("/{document_id}/fields/{field_id}/review", response_model=DocumentAnalysisResponse)
def review_field(document_id: uuid.UUID, field_id: uuid.UUID, request: FieldReviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    field = db.scalar(select(ExtractedField).where(ExtractedField.id == field_id, ExtractedField.document_id == document_id, ExtractedField.is_active.is_(True)))
    if not document or not field:
        raise HTTPException(status_code=404, detail="Field not found")
    classification = db.scalar(select(ClassificationResult).where(
        ClassificationResult.document_id == document_id,
        ClassificationResult.is_active.is_(True),
    ).order_by(ClassificationResult.processed_at.desc()))
    if classification and _classification_review_required(classification):
        raise HTTPException(status_code=409, detail={"code": "classification_review_required"})
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
