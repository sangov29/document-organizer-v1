from io import BytesIO
import uuid
from urllib.parse import urlencode
from celery import Celery
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select
from app.core.config import settings
from app.core.security import create_email_verification_token, create_password_reset_token
from app.db.session import SessionLocal
from app.models import Document, OCRArtifact, Page, PreprocessingResult, ProcessingJob, User
from app.models.enums import ProcessingStatus
from app.services.email import email_service
from app.services.storage import storage
from app.services.preprocessing import preprocess_page
from app.services.ocr import recognize_page

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
        review_required = preprocessing_review or ocr_review
        # Printed-text OCR is complete. Later CL/EX stages are still pending;
        # degraded pages remain explicitly routed for review.
        document.status = ProcessingStatus.NEEDS_REVIEW if review_required else ProcessingStatus.QUEUED
        db.commit()
        return {"document_id": document_id, "status": "ocr_ready", "page_count": page_count, "needs_review": review_required}
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
