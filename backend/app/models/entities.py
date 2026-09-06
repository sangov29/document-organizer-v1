import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer,
    Index, JSON, String, Text, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.enums import (
    AuditEventType, DocumentFamily, ProcessingStatus, SensitivitySubjectType, TrustState
)


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    duplicate_of_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, name="processing_status"), default=ProcessingStatus.QUEUED)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan")
    __table_args__ = (
        Index(
            "uq_document_user_hash_canonical", "user_id", "sha256", unique=True,
            postgresql_where=text("duplicate_of_document_id IS NULL"),
        ),
    )


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    derived_object_key: Mapped[str | None] = mapped_column(String(1024))
    document = relationship("Document", back_populates="pages")
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_page_document_number"),)


class PreprocessingResult(Base):
    __tablename__ = "preprocessing_results"
    id: Mapped[uuid.UUID] = uuid_pk()
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), unique=True, index=True)
    normalized_object_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    orientation_degrees: Mapped[int | None] = mapped_column(Integer)
    orientation_confidence: Mapped[float | None] = mapped_column(Float)
    skew_degrees: Mapped[float | None] = mapped_column(Float)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    noise_reduction_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, name="job_processing_status"), default=ProcessingStatus.QUEUED)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class OCRArtifact(Base):
    __tablename__ = "ocr_artifacts"
    id: Mapped[uuid.UUID] = uuid_pk()
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), unique=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    blocks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(128), nullable=False, default="printed_text_ocr")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="eng")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_ocr_confidence"),
    )


class ClassificationResult(Base):
    __tablename__ = "classification_results"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    family: Mapped[DocumentFamily] = mapped_column(Enum(DocumentFamily, name="document_family"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_classification_confidence"),)


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    trust_state: Mapped[TrustState] = mapped_column(Enum(TrustState, name="trust_state"), nullable=False)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        CheckConstraint("criticality IN ('critical','standard')", name="ck_field_criticality"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_field_confidence"),
    )


class VisualRegion(Base):
    __tablename__ = "visual_regions"
    id: Mapped[uuid.UUID] = uuid_pk()
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    region_type: Mapped[str] = mapped_column(String(64), nullable=False)
    bbox: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)


class SensitivityTag(Base):
    __tablename__ = "sensitivity_tags"
    id: Mapped[uuid.UUID] = uuid_pk()
    subject_type: Mapped[SensitivitySubjectType] = mapped_column(Enum(SensitivitySubjectType, name="sensitivity_subject_type"), nullable=False)
    extracted_field_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extracted_fields.id", ondelete="CASCADE"))
    visual_region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("visual_regions.id", ondelete="CASCADE"))
    sensitivity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "(extracted_field_id IS NOT NULL AND visual_region_id IS NULL) OR "
            "(extracted_field_id IS NULL AND visual_region_id IS NOT NULL)",
            name="ck_sensitivity_exactly_one_subject"
        ),
    )


class Provenance(Base):
    __tablename__ = "provenance"
    id: Mapped[uuid.UUID] = uuid_pk()
    extracted_field_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extracted_fields.id", ondelete="CASCADE"), index=True)
    classification_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("classification_results.id", ondelete="CASCADE"), index=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    source_page_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    visual_region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("visual_regions.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "(extracted_field_id IS NOT NULL AND classification_result_id IS NULL) OR "
            "(extracted_field_id IS NULL AND classification_result_id IS NOT NULL)",
            name="ck_provenance_exactly_one_result"
        ),
    )


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[uuid.UUID] = uuid_pk()
    extracted_field_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_fields.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    prior_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False)
    prior_provenance_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("provenance.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType, name="audit_event_type"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
