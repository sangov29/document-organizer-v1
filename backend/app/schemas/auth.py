from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class RegisterResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=12, max_length=128)


class MessageResponse(BaseModel):
    message: str


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TotpConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class LogoutResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    is_verified: bool
    totp_enabled: bool
