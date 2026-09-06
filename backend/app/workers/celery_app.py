from io import BytesIO
import uuid
from urllib.parse import urlencode
from celery import Celery
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select
from app.core.config import settings
from app.core.security import create_email_verification_token, create_password_reset_token
from app.db.session import SessionLocal
from app.models import (
    ClassificationResult, Document, ExtractedField, OCRArtifact, Page,
    PreprocessingResult, ProcessingJob, Provenance, SensitivityTag, User,
    VisualRegion,
)
from app.models.enums import (
    DocumentFamily, ProcessingStatus, SensitivitySubjectType, TrustState,
)
from app.services.email import email_service
from app.services.storage import storage
from app.services.preprocessing import preprocess_page
from app.services.ocr import recognize_page
from app.services.sensitivity import (
    find_signature_bbox, find_value_bbox, sensitivity_type_for_field,
)
from app.services.analysis import (
    MODEL_VERSION as ANALYSIS_MODEL_VERSION,
    PROVIDER as ANALYSIS_PROVIDER,
    classify_text, extract_predefined_fields, extract_unknown_fields,
)

celery = Celery("document_organizer", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.task_track_started = True


@celery.task(name="auth.send_verification_email")
def send_verification_email(email: str):
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if not user or user.is_verified:
            return {"status": "noop"}
        token = create_email_verification_token(str(user.id), user.verification_version)
        url = f"{settings.verification_frontend_url}?{urlencode({'token': token})}"
        email_service.send_verification(user.email, url)
        return {"status": "sent"}
    finally:
        db.close()


@celery.task(name="auth.send_password_reset_email")
def send_password_reset_email(email: str):
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if not user or not user.is_verified:
            return {"status": "noop"}
        token = create_password_reset_token(str(user.id), user.reset_version)
        url = f"{settings.password_reset_frontend_url}?{urlencode({'token': token})}"
        email_service.send_password_reset(user.email, url)
        return {"status": "sent"}
    finally:
        db.close()


def _write_pdf_page(document: Document, page_number: int, writer: PdfWriter) -> str:
    key = f"users/{document.user_id}/documents/{document.id}/pages/{page_number}.pdf"
    if not storage.exists(key):
        output = BytesIO()
        writer.write(output)
        storage.put_immutable(key, output.getvalue(), "application/pdf")
    return key


def _split_pages(db, document: Document) -> int:
    existing_pages = {
        page.page_number: page
        for page in db.scalars(select(Page).where(Page.document_id == document.id)).all()
    }

    if document.mime_type == "application/pdf":
        source = storage.get_bytes(document.object_key)
        reader = PdfReader(BytesIO(source))
        if len(reader.pages) == 0:
            raise ValueError("PDF contains no pages")
        for index, pdf_page in enumerate(reader.pages, start=1):
            if index in existing_pages:
                continue
            writer = PdfWriter()
            writer.add_page(pdf_page)
            key = _write_pdf_page(document, index, writer)
            db.add(Page(document_id=document.id, page_number=index, derived_object_key=key))
        db.flush()
        return len(reader.pages)

    # JPG/PNG are logical single-page documents; their Page references the
    # immutable source object rather than creating a redundant derived copy.
    if 1 not in existing_pages:
        db.add(Page(document_id=document.id, page_number=1, derived_object_key=document.object_key))
        db.flush()
    return 1


def _preprocess_pages(db, document: Document, correlation_id: str) -> tuple[int, bool]:
    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()
    review_required = False
    for page in pages:
        existing = db.scalar(select(PreprocessingResult).where(PreprocessingResult.page_id == page.id))
        if existing:
            review_required = review_required or existing.needs_review
            continue
        job = ProcessingJob(
            document_id=document.id, page_id=page.id, stage="preprocessing",
            status=ProcessingStatus.PROCESSING, correlation_id=correlation_id,
        )
        db.add(job)
        db.flush()
        source = storage.get_bytes(page.derived_object_key)
        page_mime = "application/pdf" if page.derived_object_key.endswith(".pdf") else document.mime_type
        result = preprocess_page(source, page_mime)
        key = f"users/{document.user_id}/documents/{document.id}/pages/{page.page_number}.normalized.png"
        storage.put_immutable(key, result.png, "image/png")
        db.add(PreprocessingResult(
            page_id=page.id,
            normalized_object_key=key,
            orientation_degrees=result.orientation_degrees,
            orientation_confidence=result.orientation_confidence,
            skew_degrees=result.skew_degrees,
            quality_status=result.quality_status,
            quality_metadata=result.quality_metadata,
            needs_review=result.needs_review,
            noise_reduction_applied=result.noise_reduction_applied,
        ))
        job.status = ProcessingStatus.NEEDS_REVIEW if result.needs_review else ProcessingStatus.READY
        review_required = review_required or result.needs_review
        db.flush()
    return len(pages), review_required


def _ocr_pages(db, document: Document, correlation_id: str) -> tuple[int, bool]:
    pages = db.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_number)
    ).all()
    review_required = False
    for page in pages:
        existing = db.scalar(select(OCRArtifact).where(OCRArtifact.page_id == page.id))
        if existing:
            review_required = review_required or not existing.text or (
                existing.confidence is None or existing.confidence < settings.ocr_review_confidence
            )
            continue
        preprocessing = db.scalar(
            select(PreprocessingResult).where(PreprocessingResult.page_id == page.id)
        )
        if not preprocessing:
            raise RuntimeError("PreprocessingResult missing before OCR")
        job = ProcessingJob(
            document_id=document.id, page_id=page.id, stage="ocr",
            status=ProcessingStatus.PROCESSING, correlation_id=correlation_id,
        )
        db.add(job)
        db.flush()
        result = recognize_page(storage.get_bytes(preprocessing.normalized_object_key))
        low_confidence = not result.text or (
            result.confidence is None or result.confidence < settings.ocr_review_confidence
        )
        db.add(OCRArtifact(
            page_id=page.id, text=result.text, confidence=result.confidence,
            blocks=result.blocks, provider=result.provider,
            model_version=result.model_version, method=result.method,
            language=result.language,
        ))
        job.status = ProcessingStatus.NEEDS_REVIEW if low_confidence else ProcessingStatus.READY
        review_required = review_required or low_confidence
        db.flush()
    return len(pages), review_required


def _analyze_document(db, document: Document, correlation_id: str) -> tuple[DocumentFamily, bool]:
    existing = db.scalar(
        select(ClassificationResult).where(
            ClassificationResult.document_id == document.id,
            ClassificationResult.is_active.is_(True),
        ).order_by(ClassificationResult.processed_at.desc())
    )
    if existing:
        return existing.family, existing.confidence < settings.classification_known_threshold

    rows = db.execute(
        select(Page, OCRArtifact)
        .join(OCRArtifact, OCRArtifact.page_id == Page.id)
        .where(Page.document_id == document.id)
        .order_by(Page.page_number)
    ).all()
    if not rows:
        raise RuntimeError("OCRArtifact missing before classification")

    job = ProcessingJob(
        document_id=document.id, stage="classification_extraction",
        status=ProcessingStatus.PROCESSING, correlation_id=correlation_id,
    )
    db.add(job)
    db.flush()
    combined_text = "\n".join(artifact.text for _, artifact in rows)
    decision = classify_text(combined_text)
    classification = ClassificationResult(
        document_id=document.id, family=decision.family,
        confidence=decision.confidence, provider=decision.provider,
        model_version=decision.model_version, method=decision.method,
        is_active=True,
    )
    db.add(classification)
    db.flush()
    first_page = rows[0][0]
    db.add(Provenance(
        classification_result_id=classification.id,
        source_document_id=document.id, source_page_id=first_page.id,
        provider=decision.provider, model_version=decision.model_version,
        method=decision.method, confidence=decision.confidence,
    ))

    field_review = False
    field_decisions = (
        extract_unknown_fields(combined_text)
        if decision.family == DocumentFamily.UNKNOWN
        else extract_predefined_fields(decision.family, combined_text)
    )
    if field_decisions:
        extraction_method = (
            "generic_unknown_rules"
            if decision.family == DocumentFamily.UNKNOWN
            else "predefined_field_rules"
        )
        for field_decision in field_decisions:
            field = ExtractedField(
                document_id=document.id, field_name=field_decision.name,
                value=field_decision.value, confidence=field_decision.confidence,
                trust_state=field_decision.trust_state,
                criticality=field_decision.criticality,
                schema_version=field_decision.schema_version,
                is_active=True,
            )
            db.add(field)
            db.flush()
            sensitivity_type = sensitivity_type_for_field(field_decision.name)
            visual_region = None
            if sensitivity_type and field_decision.value:
                bbox = find_value_bbox(rows[0][1].blocks, field_decision.value)
                if bbox:
                    visual_region = VisualRegion(
                        page_id=first_page.id, region_type="sensitive_field",
                        bbox=bbox, confidence=field_decision.confidence,
                        provider=ANALYSIS_PROVIDER,
                        model_version=field_decision.schema_version or ANALYSIS_MODEL_VERSION,
                    )
                    db.add(visual_region)
                    db.flush()
            db.add(Provenance(
                extracted_field_id=field.id,
                source_document_id=document.id, source_page_id=first_page.id,
                visual_region_id=visual_region.id if visual_region else None,
                provider=ANALYSIS_PROVIDER,
                model_version=field_decision.schema_version or ANALYSIS_MODEL_VERSION,
                method=extraction_method, confidence=field_decision.confidence,
            ))
            if sensitivity_type:
                db.add(SensitivityTag(
                    subject_type=SensitivitySubjectType.EXTRACTED_FIELD,
                    extracted_field_id=field.id,
                    sensitivity_type=sensitivity_type,
                ))
            field_review = field_review or (
                (
                    field_decision.criticality == "critical"
                    and field_decision.trust_state == TrustState.NOT_FOUND
                )
                or
                field_decision.trust_state == TrustState.UNCERTAIN
                or (
                    field_decision.confidence is not None
                    and field_decision.confidence < settings.field_review_confidence
                )
            )
    if decision.family == DocumentFamily.BANKING:
        signature_bbox = find_signature_bbox(rows[0][1].blocks)
        if signature_bbox:
            signature_region = VisualRegion(
                page_id=first_page.id, region_type="signature",
                bbox=signature_bbox, confidence=rows[0][1].confidence,
                provider=rows[0][1].provider, model_version=rows[0][1].model_version,
            )
            db.add(signature_region)
            db.flush()
            db.add(SensitivityTag(
                subject_type=SensitivitySubjectType.VISUAL_REGION,
                visual_region_id=signature_region.id,
                sensitivity_type="signature",
            ))
    classification_review = (
        decision.family != DocumentFamily.UNKNOWN
        and decision.confidence < settings.classification_known_threshold
    )
    job.status = ProcessingStatus.NEEDS_REVIEW if classification_review or field_review else ProcessingStatus.READY
    db.flush()
    return decision.family, classification_review or field_review


@celery.task(name="pipeline.bootstrap", bind=True, autoretry_for=(RuntimeError,), retry_backoff=True, max_retries=3)
def bootstrap_pipeline(self, document_id: str):
    db = SessionLocal()
    document_uuid = None
    active_stage = "ingestion"
    correlation_id = uuid.uuid4().hex
    try:
        document_uuid = uuid.UUID(document_id)
        document = db.get(Document, document_uuid)
        if not document:
            return {"document_id": document_id, "status": "missing"}

        job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document.id, ProcessingJob.stage == "ingestion")
            .order_by(ProcessingJob.created_at.desc())
        )
        if not job:
            raise RuntimeError("Ingestion ProcessingJob missing")
        correlation_id = job.correlation_id

        job.status = ProcessingStatus.PROCESSING
        document.status = ProcessingStatus.PROCESSING
        db.commit()

        page_count = _split_pages(db, document)
        job.status = ProcessingStatus.READY
        db.commit()

        active_stage = "preprocessing"
        _, preprocessing_review = _preprocess_pages(db, document, job.correlation_id)
        db.commit()

        active_stage = "ocr"
        _, ocr_review = _ocr_pages(db, document, job.correlation_id)
        db.commit()

        active_stage = "classification_extraction"
        family, analysis_review = _analyze_document(db, document, job.correlation_id)
        review_required = preprocessing_review or ocr_review
        review_required = review_required or analysis_review
        # Printed-text OCR is complete. Later CL/EX stages are still pending;
        # degraded pages remain explicitly routed for review.
        document.status = ProcessingStatus.NEEDS_REVIEW if review_required else ProcessingStatus.QUEUED
        db.commit()
        return {
            "document_id": document_id, "status": "analysis_ready",
            "page_count": page_count, "family": family.value,
            "needs_review": review_required,
        }
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_uuid) if document_uuid else None
        if document:
            document.status = ProcessingStatus.FAILED
            failed_jobs = db.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.document_id == document.id,
                    ProcessingJob.stage == active_stage,
                    ProcessingJob.status == ProcessingStatus.PROCESSING,
                )
            ).all()
            if not failed_jobs:
                failed_jobs = [ProcessingJob(
                    document_id=document.id, stage=active_stage,
                    status=ProcessingStatus.FAILED, correlation_id=correlation_id,
                )]
                db.add(failed_jobs[0])
            for failed_job in failed_jobs:
                failed_job.status = ProcessingStatus.FAILED
                failed_job.error_code = exc.__class__.__name__
            db.commit()
        raise
    finally:
        db.close()
