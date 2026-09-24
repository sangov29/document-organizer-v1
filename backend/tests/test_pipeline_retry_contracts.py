from types import SimpleNamespace
import uuid

from app.models.enums import ProcessingStatus
from app.workers import celery_app


class _Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _RetrySession:
    def __init__(self, pages, artifacts):
        self.pages = pages
        self.artifacts = iter(artifacts)
        self.added = []

    def scalars(self, _query):
        return _Rows(self.pages)

    def scalar(self, _query):
        return next(self.artifacts)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None


def test_ocr_retry_reuses_committed_artifact_without_double_processing(monkeypatch):
    """A redelivered task must not OCR or write an already completed page twice."""
    page = SimpleNamespace(id=uuid.uuid4(), page_number=1)
    artifact = SimpleNamespace(text="recognized", confidence=0.99)
    session = _RetrySession([page], [artifact])

    def unexpected_recognition(_png):
        raise AssertionError("committed OCR must be reused on retry")

    monkeypatch.setattr(celery_app, "recognize_page", unexpected_recognition)

    count, needs_review = celery_app._ocr_pages(
        session,
        SimpleNamespace(id=uuid.uuid4()),
        "retry-correlation",
    )

    assert count == 1
    assert needs_review is False
    assert session.added == []


def test_ocr_retry_preserves_review_state_of_committed_artifact(monkeypatch):
    """Idempotent reuse must not lose a prior low-confidence review decision."""
    page = SimpleNamespace(id=uuid.uuid4(), page_number=1)
    artifact = SimpleNamespace(text="", confidence=None)
    session = _RetrySession([page], [artifact])
    monkeypatch.setattr(
        celery_app,
        "recognize_page",
        lambda _png: (_ for _ in ()).throw(AssertionError("OCR reran")),
    )

    count, needs_review = celery_app._ocr_pages(
        session,
        SimpleNamespace(id=uuid.uuid4(), status=ProcessingStatus.PROCESSING),
        "retry-correlation",
    )

    assert count == 1
    assert needs_review is True
    assert session.added == []
