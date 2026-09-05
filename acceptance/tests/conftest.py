from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Document, Page, PreprocessingResult, ProcessingJob, User

API_URL = os.getenv("ACCEPTANCE_API_URL", "http://localhost:8000/api/v1")
MAILPIT_URL = os.getenv("MAILPIT_API_URL", "http://mailpit:8025")
RUN_ID = os.getenv("ACCEPTANCE_RUN_ID", uuid.uuid4().hex[:12])
EVIDENCE_DIR = Path(os.getenv("ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER", "/evidence"))

SENSITIVE_KEYS = {
    "access_token", "token", "password", "new_password", "totp_code", "secret",
    "provisioning_uri", "authorization", "jwt", "reset_link", "verification_link",
}
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
TOKEN_QUERY_RE = re.compile(r"([?&]token=)[^&\s]+", re.I)
BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~-]+", re.I)


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted>" if k.lower() in SENSITIVE_KEYS else sanitize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        value = JWT_RE.sub("<redacted-jwt>", value)
        value = TOKEN_QUERY_RE.sub(r"\1<redacted>", value)
        value = BEARER_RE.sub(r"\1<redacted>", value)
        return value
    return value


def safe_body(response: httpx.Response) -> Any:
    try:
        return sanitize(response.json())
    except Exception:
        text = response.text[:2000]
        return sanitize(text)


@dataclass
class EvidenceRecorder:
    nodeid: str
    responses: list[dict[str, Any]] = field(default_factory=list)
    document_ids: set[str] = field(default_factory=set)
    notes: list[dict[str, Any]] = field(default_factory=list)

    def response(self, label: str, response: httpx.Response) -> None:
        self.responses.append({
            "label": label,
            "method": response.request.method,
            "url_path": response.request.url.path,
            "status": response.status_code,
            "body": safe_body(response),
            "request_id": response.headers.get("x-request-id") or response.headers.get("x-correlation-id"),
        })

    def document(self, document_id: str | None) -> None:
        if document_id:
            self.document_ids.add(str(document_id))

    def note(self, label: str, data: Any) -> None:
        self.notes.append({"label": label, "data": sanitize(data)})

    def diagnostics(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "test": self.nodeid,
            "responses": self.responses,
            "notes": self.notes,
            "documents": [],
        }
        if not self.document_ids:
            return result
        db = SessionLocal()
        try:
            for raw_id in sorted(self.document_ids):
                try:
                    doc_uuid = uuid.UUID(raw_id)
                except ValueError:
                    continue
                doc = db.get(Document, doc_uuid)
                jobs = db.scalars(
                    select(ProcessingJob)
                    .where(ProcessingJob.document_id == doc_uuid)
                    .order_by(ProcessingJob.created_at.asc())
                ).all()
                result["documents"].append({
                    "document_id": raw_id,
                    "document_status": doc.status.value if doc else None,
                    "worker_jobs": [
                        {
                            "stage": job.stage,
                            "status": job.status.value,
                            "error_code": job.error_code,
                            "correlation_id": job.correlation_id,
                        }
                        for job in jobs
                    ],
                })
        finally:
            db.close()
        return result


class APIClient:
    def __init__(self, recorder: EvidenceRecorder):
        self.recorder = recorder
        self.client = httpx.Client(base_url=API_URL, timeout=30.0)

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, *, label: str, token: str | None = None, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self.client.request(method, path, headers=headers, **kwargs)
        self.recorder.response(label, response)
        try:
            body = response.json()
            if isinstance(body, dict):
                if "id" in body and path.startswith("/documents"):
                    self.recorder.document(body.get("id"))
                document = body.get("document")
                if isinstance(document, dict):
                    self.recorder.document(document.get("id"))
                for item in body.get("items", []) if isinstance(body.get("items"), list) else []:
                    if isinstance(item, dict) and isinstance(item.get("document"), dict):
                        self.recorder.document(item["document"].get("id"))
        except Exception:
            pass
        return response


@pytest.fixture(autouse=True)
def catalogue_junit_properties(request, record_property):
    marker = request.node.get_closest_marker("catalogue")
    if marker:
        test_id = marker.args[0] if marker.args else marker.kwargs.get("id")
        steps = marker.kwargs.get("steps", "")
        record_property("catalogue_test_id", str(test_id))
        record_property("catalogue_steps", str(steps))
    if request.node.get_closest_marker("known_gap"):
        record_property("catalogue_known_gap", "true")


@pytest.fixture
def evidence(request) -> EvidenceRecorder:
    return EvidenceRecorder(nodeid=request.node.nodeid)


@pytest.fixture
def api(evidence: EvidenceRecorder):
    client = APIClient(evidence)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def run_id() -> str:
    return RUN_ID


def unique_email(label: str) -> str:
    return f"acceptance+{RUN_ID}-{label}-{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def email_factory():
    return unique_email


@pytest.fixture
def password_factory():
    def make(label: str = "pw") -> str:
        # Synthetic only. Never written to evidence.
        return f"Acceptance-{label}-{uuid.uuid4().hex[:12]}!9x"
    return make


def wait_for_mail_text(email: str, *, subject_phrase: str | None = None, timeout: float = 30.0) -> str:
    query = f'to:"{email}"'
    if subject_phrase:
        query += f' subject:"{subject_phrase}"'
    deadline = time.time() + timeout
    with httpx.Client(base_url=MAILPIT_URL, timeout=5.0) as client:
        while time.time() < deadline:
            response = client.get("/view/latest.txt", params={"query": query})
            if response.status_code == 200:
                return response.text
            time.sleep(0.5)
    raise AssertionError(f"Mailpit did not receive expected local message for {email}")


def extract_token_from_mail(text: str, expected_path: str) -> str:
    # Tokens are intentionally retained only in memory and never returned in diagnostics.
    match = re.search(r"https?://[^\s]+" + re.escape(expected_path) + r"\?token=([^\s]+)", text)
    if not match:
        # Frontend URL may have a different host while keeping the path.
        match = re.search(re.escape(expected_path) + r"\?token=([^\s]+)", text)
    if not match:
        raise AssertionError(f"Expected token link path {expected_path} not found in local mail")
    return match.group(1).strip()


@pytest.fixture
def verified_account(api: APIClient, email_factory, password_factory):
    email = email_factory("verified")
    password = password_factory("verified")
    reg = api.request("POST", "/auth/register", label="register verified fixture", json={"email": email, "password": password})
    assert reg.status_code == 202
    mail = wait_for_mail_text(email, subject_phrase="Verify")
    token = extract_token_from_mail(mail, "/verify-email")
    verify = api.request("POST", "/auth/verify-email", label="verify fixture", json={"token": token})
    assert verify.status_code == 200
    return {"email": email, "password": password, "user_id": verify.json()["id"]}


def login(api: APIClient, email: str, password: str, *, label: str, totp_code: str | None = None) -> httpx.Response:
    payload: dict[str, Any] = {"email": email, "password": password}
    if totp_code is not None:
        payload["totp_code"] = totp_code
    return api.request("POST", "/auth/login", label=label, json=payload)


@pytest.fixture
def auth_token(api: APIClient, verified_account):
    response = login(api, verified_account["email"], verified_account["password"], label="login fixture")
    assert response.status_code == 200
    return response.json()["access_token"]


def db_user_state(email: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if not user:
            return None
        return {
            "id": str(user.id),
            "is_verified": bool(user.is_verified),
            "totp_enabled": bool(user.totp_enabled),
            "password_is_plaintext": not str(user.password_hash).startswith("$argon2"),
            "password_scheme": "argon2" if str(user.password_hash).startswith("$argon2") else "unknown",
        }
    finally:
        db.close()


def wait_for_ingestion(document_id: str, *, expected_job_status: str = "ready", timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    doc_uuid = uuid.UUID(document_id)
    while time.time() < deadline:
        db = SessionLocal()
        try:
            doc = db.get(Document, doc_uuid)
            job = db.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == doc_uuid, ProcessingJob.stage == "ingestion")
                .order_by(ProcessingJob.created_at.desc())
            )
            if job and job.status.value == expected_job_status:
                pages = db.scalars(select(Page).where(Page.document_id == doc_uuid).order_by(Page.page_number.asc())).all()
                return {
                    "document_status": doc.status.value if doc else None,
                    "job_status": job.status.value,
                    "error_code": job.error_code,
                    "correlation_id": job.correlation_id,
                    "pages": [
                        {"page_number": p.page_number, "document_id": str(p.document_id), "derived_object_key": p.derived_object_key}
                        for p in pages
                    ],
                }
        finally:
            db.close()
        time.sleep(0.25)
    raise AssertionError(f"Ingestion job for {document_id} did not reach {expected_job_status}")


def wait_for_preprocessing(document_id: str, *, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    doc_uuid = uuid.UUID(document_id)
    while time.time() < deadline:
        db = SessionLocal()
        try:
            doc = db.get(Document, doc_uuid)
            pages = db.scalars(select(Page).where(Page.document_id == doc_uuid).order_by(Page.page_number)).all()
            results = []
            for page in pages:
                result = db.scalar(select(PreprocessingResult).where(PreprocessingResult.page_id == page.id))
                if result:
                    results.append({
                        "page_id": str(page.id), "page_number": page.page_number,
                        "normalized_object_key": result.normalized_object_key,
                        "orientation_degrees": result.orientation_degrees,
                        "orientation_confidence": result.orientation_confidence,
                        "skew_degrees": result.skew_degrees,
                        "quality_status": result.quality_status,
                        "quality_metadata": result.quality_metadata,
                        "needs_review": result.needs_review,
                        "noise_reduction_applied": result.noise_reduction_applied,
                    })
            if pages and len(results) == len(pages):
                return {"document_status": doc.status.value, "pages": results}
        finally:
            db.close()
        time.sleep(0.25)
    raise AssertionError(f"Preprocessing for {document_id} did not complete")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    recorder = item.funcargs.get("evidence")
    if not isinstance(recorder, EvidenceRecorder):
        return
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid)[:180] + ".failure.json"
    (EVIDENCE_DIR / filename).write_text(json.dumps(recorder.diagnostics(), indent=2, sort_keys=True))


def pytest_configure(config):
    config.addinivalue_line("markers", "catalogue(id, steps): frozen catalogue mapping")
    config.addinivalue_line("markers", "known_gap: public capability required by a catalogue substep is absent")
