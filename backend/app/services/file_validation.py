from __future__ import annotations


SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


def content_matches_declared_type(data: bytes, declared_type: str | None) -> bool:
    """Validate supported upload types by stable file signatures.

    This deliberately verifies the container signature only. Deeper structural
    corruption remains a worker concern so malformed-but-identifiable PDFs can
    fail safely and observably in the asynchronous pipeline.
    """
    signatures = SIGNATURES.get(declared_type or "")
    return bool(signatures and any(data.startswith(signature) for signature in signatures))
