from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    idle_session_minutes: int = 30
    verification_token_minutes: int = 30
    verification_frontend_url: str = "http://localhost:3000/verify-email"
    password_reset_token_minutes: int = 30
    password_reset_frontend_url: str = "http://localhost:3000/reset-password"
    totp_fernet_key: str
    totp_issuer: str = "Document Organizer"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@example.invalid"
    smtp_starttls: bool = True
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "documents"
    s3_region: str = "us-east-1"
    redis_url: str
    max_upload_bytes: int = 20 * 1024 * 1024
    pp_min_width: int = 600
    pp_min_height: int = 800
    pp_blur_threshold: float = 55.0
    pp_contrast_threshold: float = 24.0
    pp_orientation_confidence: float = 5.0
    pp_deskew_max_degrees: float = 15.0
    pp_noise_reduction_enabled: bool = False
    ocr_provider: str = "paddleocr"
    ocr_model_version: str = "PP-OCRv5_mobile_det+en_PP-OCRv5_mobile_rec"
    ocr_language: str = "en"
    ocr_paddle_detection_model: str = "PP-OCRv5_mobile_det"
    ocr_paddle_recognition_model: str = "en_PP-OCRv5_mobile_rec"
    ocr_paddle_device: str = "cpu"
    ocr_paddle_enable_mkldnn: bool = False
    ocr_paddle_cpu_threads: int = 1
    ocr_tesseract_language: str = "eng"
    ocr_tesseract_config: str = "--oem 1 --psm 6"
    ocr_review_confidence: float = 0.60
    classification_known_threshold: float = 0.50
    field_review_confidence: float = 0.75

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
