import uuid
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import AuthContext, get_auth_context
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_email_verification_token,
    decode_password_reset_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    hash_password,
    totp_provisioning_uri,
    verify_password,
    verify_totp_code,
)
from app.db.session import get_db
from app.models import AuditEvent, User
from app.models.enums import AuditEventType
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    TotpConfirmRequest,
    TotpSetupResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.session_store import session_store
from app.workers.celery_app import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])


def user_response(user: User) -> UserResponse:
    return UserResponse(id=str(user.id), email=user.email, is_verified=user.is_verified, totp_enabled=user.totp_enabled)


@router.post("/register", response_model=RegisterResponse, status_code=202)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if not existing:
        user = User(email=email, password_hash=hash_password(payload.password), is_verified=False)
        db.add(user)
        db.flush()
        db.add(AuditEvent(
            user_id=user.id,
            event_type=AuditEventType.AUTH_SECURITY,
            target_type="user",
            target_id=str(user.id),
            metadata_json={"action": "registration"},
        ))
        db.commit()
    else:
        # Equalize deliberately expensive password hashing. Email delivery is
        # also queued for both branches so synchronous SMTP behavior cannot
        # become a new registration enumeration signal.
        hash_password(payload.password)

    send_verification_email.delay(email)
    return RegisterResponse(message="If registration can proceed, verification instructions will be sent.")


@router.post("/verify-email", response_model=UserResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    try:
        token_payload = decode_email_verification_token(payload.token)
        user_id = uuid.UUID(token_payload["sub"])
        verification_version = int(token_payload["vv"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user = db.get(User, user_id)
    if not user or user.is_verified or user.verification_version != verification_version:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user.is_verified = True
    user.verification_version += 1
    db.add(AuditEvent(
        user_id=user.id,
        event_type=AuditEventType.AUTH_SECURITY,
        target_type="user",
        target_id=str(user.id),
        metadata_json={"action": "email_verified"},
    ))
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.post("/password-reset/request", response_model=MessageResponse, status_code=202)
def request_password_reset(payload: PasswordResetRequest):
    # Deliberately do not query account existence here. Every request enqueues
    # the same async operation and receives the same response. The worker owns
    # the account-dependent no-op/send decision outside the request timing path.
    send_password_reset_email.delay(payload.email.lower())
    return MessageResponse(message="If the account can be reset, instructions will be sent.")


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    try:
        token_payload = decode_password_reset_token(payload.token)
        user_id = uuid.UUID(token_payload["sub"])
        reset_version = int(token_payload["rv"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = db.get(User, user_id)
    if not user or user.reset_version != reset_version:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.password_hash = hash_password(payload.new_password)
    user.reset_version += 1
    db.add(AuditEvent(
        user_id=user.id,
        event_type=AuditEventType.AUTH_SECURITY,
        target_type="user",
        target_id=str(user.id),
        metadata_json={"action": "password_reset"},
    ))
    # Revoke before committing the credential change. If Redis is unavailable,
    # fail the reset rather than accepting a new password while leaving old
    # authenticated sessions alive. A DB failure after revocation is safe: the
    # old password remains valid but sessions must be re-established.
    session_store.revoke_all(str(user.id))
    db.commit()
    return MessageResponse(message="Password reset complete. Please log in again.")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    password_hash_to_check = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid_password = verify_password(payload.password, password_hash_to_check)
    if not valid_password or not user or not user.is_verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.totp_enabled:
        if not user.totp_secret_ciphertext or not payload.totp_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        try:
            totp_secret = decrypt_totp_secret(user.totp_secret_ciphertext)
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not verify_totp_code(totp_secret, payload.totp_code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    session_id = uuid.uuid4().hex
    session_store.create(session_id, str(user.id))
    db.add(AuditEvent(
        user_id=user.id,
        event_type=AuditEventType.AUTH_SECURITY,
        target_type="user",
        target_id=str(user.id),
        metadata_json={"action": "login_success", "session_id": session_id},
    ))
    db.commit()
    return TokenResponse(access_token=create_access_token(str(user.id), session_id))


@router.post("/totp/setup", response_model=TotpSetupResponse)
def setup_totp(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    user = context.user
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="TOTP is already enabled")
    secret = generate_totp_secret()
    user.totp_secret_ciphertext = encrypt_totp_secret(secret)
    db.commit()
    return TotpSetupResponse(secret=secret, provisioning_uri=totp_provisioning_uri(secret, user.email))


@router.post("/totp/confirm", response_model=UserResponse)
def confirm_totp(payload: TotpConfirmRequest, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    user = context.user
    if user.totp_enabled or not user.totp_secret_ciphertext:
        raise HTTPException(status_code=400, detail="TOTP setup is not pending")
    try:
        secret = decrypt_totp_secret(user.totp_secret_ciphertext)
    except Exception:
        raise HTTPException(status_code=400, detail="TOTP setup is not pending")
    if not verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.totp_enabled = True
    db.add(AuditEvent(
        user_id=user.id,
        event_type=AuditEventType.AUTH_SECURITY,
        target_type="user",
        target_id=str(user.id),
        metadata_json={"action": "totp_enabled"},
    ))
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.post("/totp/disable", response_model=UserResponse)
def disable_totp(payload: TotpConfirmRequest, context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    user = context.user
    if not user.totp_enabled or not user.totp_secret_ciphertext:
        raise HTTPException(status_code=400, detail="TOTP is not enabled")
    try:
        secret = decrypt_totp_secret(user.totp_secret_ciphertext)
    except Exception:
        raise HTTPException(status_code=400, detail="TOTP is not enabled")
    if not verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.totp_enabled = False
    user.totp_secret_ciphertext = None
    db.add(AuditEvent(
        user_id=user.id,
        event_type=AuditEventType.AUTH_SECURITY,
        target_type="user",
        target_id=str(user.id),
        metadata_json={"action": "totp_disabled"},
    ))
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.post("/logout", response_model=LogoutResponse)
def logout(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    session_store.revoke(context.session_id)
    db.add(AuditEvent(
        user_id=context.user.id,
        event_type=AuditEventType.AUTH_SECURITY,
        target_type="user",
        target_id=str(context.user.id),
        metadata_json={"action": "logout", "session_id": context.session_id},
    ))
    db.commit()
    return LogoutResponse(message="Logged out")
