from __future__ import annotations

import hashlib
import struct
import zlib
from io import BytesIO

from pypdf import PdfWriter
from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
    tag = _tag(run_id, label)
    colour = tuple(bytes.fromhex(tag[:6]))
    image = Image.new("RGB", (64, 64), colour)
    output = BytesIO()
    image.save(output, "JPEG", quality=90, optimize=False, progressive=False)
    base = output.getvalue()

    comment = f"{run_id}:{label}:{tag}".encode()
    segment = b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment
    data = base[:2] + segment + base[2:]
    with Image.open(BytesIO(data)) as decoded:
        decoded.load()
    return data


def malformed_pdf_bytes(run_id: str, label: str) -> bytes:
    return f"%PDF-1.7\n% malformed acceptance {run_id}:{label}\n1 0 obj << /Broken true >>\n".encode()


def unsupported_bytes(run_id: str, label: str) -> bytes:
    return f"unsupported acceptance fixture {run_id}:{label}:{_tag(run_id, label)}\n".encode()


def document_png(run_id: str, label: str, *, rotation: float = 0, blur: float = 0,
                 contrast: str = "normal", size: tuple[int, int] = (1200, 1600),
                 lines: list[str] | None = None) -> bytes:
    background = 245 if contrast == "normal" else 145
    foreground = 15 if contrast == "normal" else 135
    image = Image.new("RGB", size, (background,) * 3)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 38)
    except OSError:
        font = ImageFont.load_default()
    lines = (lines or [
        "DOCUMENT ORGANIZER ACCEPTANCE PAGE",
        f"Run {run_id} Fixture {label}",
        "Name: Synthetic Example Customer",
        "Reference: PP-TEST-2026-0001",
        "Date: 05 September 2026",
        "This page contains repeated readable text for orientation.",
    ]) * 4
    for index, line in enumerate(lines):
        draw.text((80, 70 + index * 58), line, fill=(foreground,) * 3, font=font)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    if rotation:
        image = image.rotate(rotation, expand=True, fillcolor=(background,) * 3)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()
