import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditEvent, ClassificationResult, Document, ExtractedField, SensitivityTag,
    ShareLink, User,
)
from app.models.enums import AuditEventType
from app.schemas.documents import (
    ShareCreateRequest, ShareCreateResponse, ShareListItemResponse,
    SharedDocumentResponse, SharedFieldResponse,
)
from app.services.rate_limiter import rate_limiter
from app.services.sensitivity import mask_sensitive_value

router = APIRouter(tags=["shares"])


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _owned_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user.id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _share_item(link: ShareLink) -> ShareListItemResponse:
    return ShareListItemResponse(
        id=str(link.id), expires_at=link.expires_at,
        revoked_at=link.revoked_at, created_at=link.created_at,
    )


@router.post("/documents/{document_id}/shares", response_model=ShareCreateResponse, status_code=201)
def create_document_share(
    document_id: uuid.UUID,
    payload: ShareCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = _owned_document(db, user, document_id)
    # A public share is a structured, masked projection of the active
    # classification and fields.  Do not issue a bearer token until that
    # projection can actually be produced: otherwise a successfully-created
    # link initially resolves to the same 404 used for invalid tokens.
    analysis_ready = db.scalar(select(ClassificationResult.id).where(
        ClassificationResult.document_id == document.id,
        ClassificationResult.is_active.is_(True),
    ))
    if analysis_ready is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "document_not_ready",
                "message": "Document analysis must complete before sharing",
            },
        )
    link_id = uuid.uuid4()
    secret = secrets.token_urlsafe(32)
    token = f"{link_id}.{secret}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)
    link = ShareLink(
        id=link_id,
        document_id=document.id, user_id=user.id,
        token_digest=_token_digest(secret), expires_at=expires_at,
    )
    db.add(link)
    db.flush()
    db.add(AuditEvent(
        user_id=user.id, event_type=AuditEventType.AUTH_SECURITY,
        target_type="document", target_id=str(document.id),
        metadata_json={
            "action": "share_created", "share_id": str(link.id),
            "expires_at": expires_at.isoformat(),
        },
    ))
    db.commit()
    db.refresh(link)
    return ShareCreateResponse(id=str(link.id), token=token, expires_at=link.expires_at)


@router.get("/documents/{document_id}/shares", response_model=list[ShareListItemResponse])
def list_document_shares(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = _owned_document(db, user, document_id)
    links = db.scalars(
        select(ShareLink).where(
            ShareLink.document_id == document.id, ShareLink.user_id == user.id,
        ).order_by(ShareLink.created_at.desc())
    ).all()
    return [_share_item(link) for link in links]


@router.delete("/documents/{document_id}/shares/{share_id}", status_code=204)
def revoke_document_share(
    document_id: uuid.UUID,
    share_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = _owned_document(db, user, document_id)
    link = db.scalar(select(ShareLink).where(
        ShareLink.id == share_id,
        ShareLink.document_id == document.id,
        ShareLink.user_id == user.id,
    ))
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    if link.revoked_at is None:
        link.revoked_at = datetime.now(timezone.utc)
        db.add(AuditEvent(
            user_id=user.id, event_type=AuditEventType.AUTH_SECURITY,
            target_type="document", target_id=str(document.id),
            metadata_json={"action": "share_revoked", "share_id": str(link.id)},
        ))
        db.commit()
    return Response(status_code=204)


@router.get("/shares/{token}", response_model=SharedDocumentResponse)
def view_shared_document(token: str, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    # Keyed on the presented token itself (hashed internally by
    # RateLimiter.key -- no raw token or client data ever becomes part of
    # the Redis key), so each link has its own independent budget: hammering
    # one shared link cannot exhaust or affect any other link's limit, and
    # this check runs before any validity check so malformed/forged tokens
    # are throttled identically to real ones.
    if not rate_limiter.allowed(
        "share-view", token, settings.share_view_rate_limit, settings.share_view_rate_window_seconds,
    ):
        raise HTTPException(
            status_code=429, detail="Too many requests for this share link",
            headers={"Retry-After": str(settings.share_view_rate_window_seconds)},
        )
    now = datetime.now(timezone.utc)
    try:
        raw_link_id, secret = token.split(".", 1)
        link_id = uuid.UUID(raw_link_id)
        if not secret:
            raise ValueError
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Shared document not found")
    link = db.get(ShareLink, link_id)
    if (
        not link
        or not hmac.compare_digest(link.token_digest, _token_digest(secret))
        or link.revoked_at is not None
        or link.expires_at <= now
    ):
        raise HTTPException(status_code=404, detail="Shared document not found")
    document = db.get(Document, link.document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Shared document not found")
    classification = db.scalar(select(ClassificationResult).where(
        ClassificationResult.document_id == document.id,
        ClassificationResult.is_active.is_(True),
    ).order_by(ClassificationResult.processed_at.desc()))
    if not classification:
        raise HTTPException(status_code=404, detail="Shared document not found")
    fields = db.scalars(select(ExtractedField).where(
        ExtractedField.document_id == document.id,
        ExtractedField.is_active.is_(True),
    ).order_by(ExtractedField.field_name)).all()
    shared_fields = []
    for field in fields:
        sensitive = db.scalar(select(SensitivityTag.id).where(
            SensitivityTag.extracted_field_id == field.id
        )) is not None
        shared_fields.append(SharedFieldResponse(
            field_name=field.field_name,
            value=mask_sensitive_value(field.value) if sensitive else field.value,
            trust_state=field.trust_state.value,
            sensitive=sensitive,
            masked=sensitive and field.value is not None,
        ))
    db.add(AuditEvent(
        user_id=link.user_id, event_type=AuditEventType.AUTH_SECURITY,
        target_type="document", target_id=str(document.id),
        metadata_json={"action": "share_accessed", "share_id": str(link.id)},
    ))
    db.commit()
    return SharedDocumentResponse(
        original_filename=document.original_filename,
        family=classification.family.value,
        version_number=document.version_number,
        expires_at=link.expires_at,
        fields=shared_fields,
    )
