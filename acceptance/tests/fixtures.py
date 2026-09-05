from __future__ import annotations

import base64
import hashlib
import struct
import zlib
from io import BytesIO

from pypdf import PdfWriter

# Tiny valid JPEG, used as a deterministic base and made unique with a JPEG COM segment.
_JPEG_BASE = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/"
    "xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/Aaf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/Aaf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Aqf/"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/"
    "2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z"
)


def _tag(run_id: str, label: str) -> str:
    return hashlib.sha256(f"{run_id}:{label}".encode()).hexdigest()[:24]


def pdf_bytes(run_id: str, label: str, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for index in range(pages):
        writer.add_blank_page(width=300 + index, height=400 + index)
    writer.add_metadata({"/AcceptanceRun": run_id, "/Fixture": label, "/Tag": _tag(run_id, label)})
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def padded_pdf_bytes(run_id: str, label: str, target_size: int) -> bytes:
    data = pdf_bytes(run_id, label, pages=1)
    if len(data) > target_size:
        raise ValueError("target_size too small")
    # PDF readers permit trailing bytes after %%EOF; this preserves a parseable fixture.
    return data + (b"\n% acceptance-padding " + _tag(run_id, label).encode()) * ((target_size - len(data)) // 45 + 1)


def exact_size_pdf(run_id: str, label: str, target_size: int) -> bytes:
    return padded_pdf_bytes(run_id, label, target_size)[:target_size]


def png_bytes(run_id: str, label: str) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\x00\x00\x00"  # filter byte + black RGB pixel
    idat_data = zlib.compress(raw)
    text_data = b"Acceptance\x00" + f"{run_id}:{label}:{_tag(run_id, label)}".encode()

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return signature + chunk(b"IHDR", ihdr_data) + chunk(b"tEXt", text_data) + chunk(b"IDAT", idat_data) + chunk(b"IEND", b"")


def jpeg_bytes(run_id: str, label: str) -> bytes:
    comment = f"{run_id}:{label}:{_tag(run_id, label)}".encode()
    segment = b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment
    if not _JPEG_BASE.startswith(b"\xff\xd8"):
        raise AssertionError("embedded JPEG fixture invalid")
    return _JPEG_BASE[:2] + segment + _JPEG_BASE[2:]


def malformed_pdf_bytes(run_id: str, label: str) -> bytes:
    return f"%PDF-1.7\n% malformed acceptance {run_id}:{label}\n1 0 obj << /Broken true >>\n".encode()


def unsupported_bytes(run_id: str, label: str) -> bytes:
    return f"unsupported acceptance fixture {run_id}:{label}:{_tag(run_id, label)}\n".encode()
