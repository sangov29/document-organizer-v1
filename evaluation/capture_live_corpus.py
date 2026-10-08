from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_value(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def discover_documents(directory: Path, expected_count: int) -> list[Path]:
    documents = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: ("annual" in path.name.casefold(), path.name.casefold()),
    )
    if len(documents) != expected_count:
        raise SystemExit(
            f"Expected exactly {expected_count} supported documents in {directory}, "
            f"but found {len(documents)}. Keep only the frozen corpus files in that folder."
        )
    return documents


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected: set[int],
    **kwargs: Any,
) -> tuple[int, Any]:
    response = client.request(method, path, **kwargs)
    if response.status_code not in expected:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:500]
        raise RuntimeError(f"{method} {path} returned {response.status_code}: {detail}")
    try:
        body = response.json()
    except Exception:
        body = None
    return response.status_code, body


def login(client: httpx.Client, email: str, password: str) -> str:
    _, body = request_json(
        client,
        "POST",
        "/auth/login",
        expected={200},
        json={"email": email, "password": password},
    )
    return body["access_token"]


def upload_document(client: httpx.Client, path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        _, body = request_json(
            client,
            "POST",
            "/documents",
            expected={202},
            data={"duplicate_action": "keep"},
            files={"file": (path.name, handle, mime_type)},
        )
    return body


def processing_snapshot(client: httpx.Client, document_id: str) -> dict[str, Any]:
    _, body = request_json(
        client, "GET", f"/documents/{document_id}", expected={200}
    )
    return body


def wait_for_capture(
    client: httpx.Client,
    document_id: str,
    *,
    timeout_seconds: int,
    poll_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    latest_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_status = processing_snapshot(client, document_id)
        if latest_status["status"] == "failed":
            raise RuntimeError(
                f"Pipeline failed: {latest_status.get('processing_message') or 'no reason provided'}"
            )

        analysis_status, analysis = request_json(
            client,
            "GET",
            f"/documents/{document_id}/analysis",
            expected={200, 202},
        )
        ocr_status, ocr = request_json(
            client,
            "GET",
            f"/documents/{document_id}/ocr",
            expected={200, 202},
        )
        if analysis_status == 200 and ocr_status == 200:
            return latest_status, analysis, ocr

        stage = latest_status.get("processing_stage") or latest_status.get("status")
        elapsed = latest_status.get("processing_elapsed_seconds")
        print(f"    waiting: {stage} ({elapsed or 0}s)", flush=True)
        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Timed out after {timeout_seconds}s; last status={latest_status.get('status')}, "
        f"stage={latest_status.get('processing_stage')}"
    )


def validate_processed_dimensions(ocr: dict[str, Any]) -> None:
    for page in ocr["pages"]:
        if (
            page.get("processed_image_width", 0) <= 0
            or page.get("processed_image_height", 0) <= 0
        ):
            raise RuntimeError(
                f"OCR page {page['page_number']} is missing processed-image dimensions"
            )


def reveal_sensitive_fields(
    client: httpx.Client, document: dict[str, Any]
) -> list[dict[str, Any]]:
    revealed: list[dict[str, Any]] = []
    analysis = document.get("analysis")
    if not analysis:
        return revealed
    for field in analysis.get("fields", []):
        if not field.get("sensitive") or field.get("value") is None:
            continue
        _, body = request_json(
            client,
            "POST",
            f"/documents/{document['document_id']}/fields/{field['id']}/reveal",
            expected={200},
        )
        revealed.append(
            {
                "field_id": field["id"],
                "field_name": field["field_name"],
                "revealed": True,
                "revealed_value": body["revealed_value"],
                "sensitivity_type": body["sensitivity_type"],
            }
        )
    return revealed


def safe_output_name(index: int, filename: str) -> str:
    stem = "".join(
        character if character.isalnum() else "-"
        for character in Path(filename).stem
    )
    stem = "-".join(part for part in stem.split("-") if part)[:80]
    return f"{index:02d}-{stem or 'document'}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture live analysis, OCR geometry, and separate sensitive reveals."
    )
    parser.add_argument("--api-url", default="http://backend:8000/api/v1")
    parser.add_argument("--documents-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--email", default=os.getenv("CAPTURE_EMAIL"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    documents = discover_documents(args.documents_dir, args.expected_count)

    dirty = git_value("status", "--porcelain")
    if dirty:
        raise SystemExit(
            "Refusing to capture from a dirty working tree. Commit or restore changes first."
        )
    commit = git_value("rev-parse", "HEAD")
    branch = git_value("branch", "--show-current")
    if branch != "main":
        raise SystemExit(
            f"Refusing to capture from branch {branch!r}. Switch to verified main first."
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    email = args.email or input("Scratch account email: ").strip()
    password = os.getenv("CAPTURE_PASSWORD") or getpass.getpass("Scratch account password: ")
    if not email or not password:
        raise SystemExit("Email and password are required.")

    capture: dict[str, Any] = {
        "capture_schema_version": "live-corpus-capture-v1",
        "started_at": utc_now(),
        "source": {"commit": commit, "branch": branch, "tree_clean": True},
        "api_url": args.api_url,
        "expected_document_count": args.expected_count,
        "capture_constraints": {
            "analysis_before_reveal": True,
            "processed_dimensions_source": "live /ocr response for normalized images",
            "reveal_database": "scratch database required",
            "scoring_performed": False,
        },
        "documents": [],
    }
    write_json(args.output_dir / "raw-capture.json", capture)

    with httpx.Client(base_url=args.api_url, timeout=60.0) as client:
        token = login(client, email, password)
        client.headers["Authorization"] = f"Bearer {token}"

        for index, path in enumerate(documents, start=1):
            print(f"[{index}/{len(documents)}] Uploading {path.name}", flush=True)
            item: dict[str, Any] = {
                "filename": path.name,
                "capture_started_at": utc_now(),
                "capture_status": "uploading",
            }
            capture["documents"].append(item)
            try:
                upload = upload_document(client, path)
                item["document_id"] = upload["id"]
                item["upload_response"] = upload
                item["capture_status"] = "processing"
                write_json(args.output_dir / "raw-capture.json", capture)

                status, analysis, ocr = wait_for_capture(
                    client,
                    upload["id"],
                    timeout_seconds=args.timeout_seconds,
                    poll_seconds=args.poll_seconds,
                )
                validate_processed_dimensions(ocr)
                item.update(
                    {
                        "capture_status": "masked_capture_complete",
                        "document_status": status,
                        "page_count": len(ocr["pages"]),
                        "analysis": analysis,
                        "ocr": ocr,
                        "masked_capture_completed_at": utc_now(),
                    }
                )
            except Exception as exc:
                item["capture_status"] = "failed"
                item["error_type"] = type(exc).__name__
                item["error"] = str(exc)
                print(f"    FAILED: {exc}", file=sys.stderr, flush=True)
            write_json(args.output_dir / safe_output_name(index, path.name), item)
            write_json(args.output_dir / "raw-capture.json", capture)

        print("Masked capture complete. Starting separate reveal pass.", flush=True)
        for index, item in enumerate(capture["documents"], start=1):
            if item.get("capture_status") != "masked_capture_complete":
                continue
            try:
                item["revealed_fields"] = reveal_sensitive_fields(client, item)
                item["reveal_pass_completed_at"] = utc_now()
                item["capture_status"] = "complete"
            except Exception as exc:
                item["capture_status"] = "reveal_failed"
                item["reveal_error_type"] = type(exc).__name__
                item["reveal_error"] = str(exc)
            write_json(
                args.output_dir / safe_output_name(index, item["filename"]), item
            )
            write_json(args.output_dir / "raw-capture.json", capture)

    capture["completed_at"] = utc_now()
    capture["summary"] = {
        "complete": sum(
            item["capture_status"] == "complete" for item in capture["documents"]
        ),
        "failed": sum(
            item["capture_status"] == "failed" for item in capture["documents"]
        ),
        "reveal_failed": sum(
            item["capture_status"] == "reveal_failed"
            for item in capture["documents"]
        ),
        "total": len(capture["documents"]),
    }
    write_json(args.output_dir / "raw-capture.json", capture)
    print(json.dumps(capture["summary"], indent=2), flush=True)
    return 0 if capture["summary"]["complete"] == args.expected_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
