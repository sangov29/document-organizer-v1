from io import BytesIO
import uuid
from urllib.parse import urlencode
from celery import Celery
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select
from app.core.config import settings
from app.core.security import create_email_verification_token, create_password_reset_token
from app.db.session import SessionLocal
from app.models import Document, Page, ProcessingJob, User
from app.models.enums import ProcessingStatus
from app.services.email import email_service
from app.services.storage import storage

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


@celery.task(name="pipeline.bootstrap", bind=True, autoretry_for=(RuntimeError,), retry_backoff=True, max_retries=3)
def bootstrap_pipeline(self, document_id: str):
    db = SessionLocal()
    document_uuid = None
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

        job.status = ProcessingStatus.PROCESSING
        document.status = ProcessingStatus.PROCESSING
        db.commit()

        page_count = _split_pages(db, document)
        job.status = ProcessingStatus.READY
        # Keep the document queued: page splitting is complete, but PP/CL/CR/EX
        # have not yet executed. READY would falsely claim end-to-end completion.
        document.status = ProcessingStatus.QUEUED
        db.commit()
        return {"document_id": document_id, "status": "pages_ready", "page_count": page_count}
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_uuid) if document_uuid else None
        if document:
            document.status = ProcessingStatus.FAILED
            job = db.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document.id, ProcessingJob.stage == "ingestion")
                .order_by(ProcessingJob.created_at.desc())
            )
            if job:
                job.status = ProcessingStatus.FAILED
                job.error_code = exc.__class__.__name__
            db.commit()
        raise
    finally:
        db.close()
