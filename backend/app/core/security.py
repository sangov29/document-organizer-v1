from datetime import datetime, timedelta, timezone
import jwt
import pyotp
from cryptography.fernet import Fernet
from pwdlib import PasswordHash
from app.core.config import settings

password_hash = PasswordHash.recommended()
_totp_fernet = Fernet(settings.totp_fernet_key.encode())

# Public, non-secret sentinel used only to make unknown-account login perform
# the same password-verification class of work as a known-account login.
# It is intentionally generated once at process startup, not per request.
DUMMY_PASSWORD_HASH = password_hash.hash("document-organizer-dummy-password-never-used")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(subject: str, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access" or not payload.get("sid"):
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def _create_versioned_token(subject: str, version: int, token_type: str, minutes: int, version_claim: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        version_claim: version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_typed_token(token: str, token_type: str, version_claim: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != token_type or version_claim not in payload:
        raise jwt.InvalidTokenError(f"Not a {token_type} token")
    return payload


def create_email_verification_token(subject: str, verification_version: int) -> str:
    return _create_versioned_token(
        subject, verification_version, "email_verification",
        settings.verification_token_minutes, "vv",
    )


def decode_email_verification_token(token: str) -> dict:
    return _decode_typed_token(token, "email_verification", "vv")


def create_password_reset_token(subject: str, reset_version: int) -> str:
    return _create_versioned_token(
        subject, reset_version, "password_reset",
        settings.password_reset_token_minutes, "rv",
    )


def decode_password_reset_token(token: str) -> dict:
    return _decode_typed_token(token, "password_reset", "rv")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    return _totp_fernet.encrypt(secret.encode()).decode()


def decrypt_totp_secret(ciphertext: str) -> str:
    return _totp_fernet.decrypt(ciphertext.encode()).decode()


def verify_totp_code(secret: str, code: str) -> bool:
    # valid_window=1 tolerates one 30-second clock step either side without
    # weakening the requirement into a reusable long-lived credential.
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.totp_issuer)
