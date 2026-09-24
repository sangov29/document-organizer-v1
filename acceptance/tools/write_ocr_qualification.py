from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

import httpx

sys.path.insert(0, "/acceptance/tests")
from fixtures import document_png  # noqa: E402

API_URL = os.getenv("ACCEPTANCE_API_URL", "http://localhost:8000/api/v1")
MAILPIT_URL = os.getenv("MAILPIT_API_URL", "http://mailpit:8025")
RUN_ID = os.getenv("ACCEPTANCE_RUN_ID", uuid.uuid4().hex[:12])
EVIDENCE_DIR = Path(os.getenv("ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER", "/evidence"))
DOCUMENTS = int(os.getenv("WRITE_OCR_DOCUMENTS", "4"))
CONCURRENCY = int(os.getenv("WRITE_OCR_CONCURRENCY", "2"))
SUBMIT_P95_MAX_SECONDS = float(os.getenv("WRITE_OCR_SUBMIT_P95_MAX_SECONDS", "3.0"))
COMPLETION_P95_MAX_SECONDS = float(os.getenv("WRITE_OCR_COMPLETION_P95_MAX_SECONDS", "150"))
TIMEOUT_SECONDS = float(os.getenv("WRITE_OCR_TIMEOUT_SECONDS", "180"))
PASSWORD = "Acceptance-Write-OCR-Synthetic!9x"


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def wait_for_verification_token(email: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    with httpx.Client(base_url=MAILPIT_URL, timeout=5.0) as client:
        while time.time() < deadline:
            response = client.get(
                "/view/latest.txt", params={"query": f'to:"{email}" subject:"Verify"'}
            )
            if response.status_code == 200:
                match = re.search(r"/verify-email\?token=([^\s]+)", response.text)
                if match:
                    return match.group(1).strip()
            time.sleep(0.5)
    raise RuntimeError("verification message was not received by the local mail sink")


def create_token() -> str:
    suffix = uuid.uuid4().hex[:8]
    email = f"acceptance+{RUN_ID[:32]}-write-{suffix}@example.com"
    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        registration = client.post("/auth/register", json={"email": email, "password": PASSWORD})
        registration.raise_for_status()
        verification = client.post(
            "/auth/verify-email", json={"token": wait_for_verification_token(email)}
        )
        verification.raise_for_status()
        login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        login.raise_for_status()
        return login.json()["access_token"]


def submit_and_wait(token: str, index: int) -> dict:
    label = f"write-ocr-{index:02d}"
    source = document_png(RUN_ID, label, size=(900, 1200))
    headers = {"Authorization": f"Bearer {token}"}
    started = time.perf_counter()
    with httpx.Client(base_url=API_URL, timeout=30.0, headers=headers) as client:
        submitted = time.perf_counter()
        response = client.post(
            "/documents", files={"file": (f"{label}.png", source, "image/png")}
        )
        submit_seconds = time.perf_counter() - submitted
        if response.status_code != 202:
            return {
                "index": index, "submit_status": response.status_code,
                "submit_seconds": submit_seconds, "completion_status": "submission_failed",
                "completion_seconds": time.perf_counter() - started,
            }
        document_id = response.json()["id"]
        deadline = time.perf_counter() + TIMEOUT_SECONDS
        last_status = None
        while time.perf_counter() < deadline:
            ocr = client.get(f"/documents/{document_id}/ocr")
            last_status = ocr.status_code
            if ocr.status_code == 200:
                pages = ocr.json().get("pages", [])
                return {
                    "index": index, "document_id": document_id,
                    "submit_status": response.status_code, "submit_seconds": submit_seconds,
                    "completion_status": "completed",
                    "completion_seconds": time.perf_counter() - started,
                    "pages": len(pages),
                    "blocks": sum(len(page.get("blocks", [])) for page in pages),
                }
            if ocr.status_code != 202:
                break
            time.sleep(0.5)
        return {
            "index": index, "document_id": document_id,
            "submit_status": response.status_code, "submit_seconds": submit_seconds,
            "completion_status": "timeout" if last_status == 202 else f"http_{last_status}",
            "completion_seconds": time.perf_counter() - started,
        }


def evaluate(results: list[dict], wall_seconds: float) -> dict:
    submit_latencies = [item["submit_seconds"] for item in results]
    completion_latencies = [item["completion_seconds"] for item in results]
    completed = [item for item in results if item["completion_status"] == "completed"]
    checks = {
        "document_count": len(results) == DOCUMENTS,
        "all_submissions_accepted": all(item["submit_status"] == 202 for item in results),
        "all_documents_completed": len(completed) == DOCUMENTS,
        "all_documents_have_ocr_evidence": all(
            item.get("pages", 0) >= 1 and item.get("blocks", 0) >= 1 for item in completed
        ),
        "submit_p95_latency": percentile(submit_latencies, 0.95) <= SUBMIT_P95_MAX_SECONDS,
        "completion_p95_latency": percentile(completion_latencies, 0.95) <= COMPLETION_P95_MAX_SECONDS,
    }
    return {
        "scope": "bounded concurrent synthetic document write and OCR completion; not a capacity claim",
        "document_count": len(results), "concurrency": CONCURRENCY,
        "wall_seconds": wall_seconds,
        "documents_per_second": len(completed) / wall_seconds if wall_seconds else 0.0,
        "submit_latency_seconds": {
            "median": statistics.median(submit_latencies) if submit_latencies else 0.0,
            "p95": percentile(submit_latencies, 0.95), "maximum": max(submit_latencies, default=0.0),
        },
        "completion_latency_seconds": {
            "median": statistics.median(completion_latencies) if completion_latencies else 0.0,
            "p95": percentile(completion_latencies, 0.95), "maximum": max(completion_latencies, default=0.0),
        },
        "targets": {
            "documents": DOCUMENTS, "concurrency": CONCURRENCY,
            "submit_p95_max_seconds": SUBMIT_P95_MAX_SECONDS,
            "completion_p95_max_seconds": COMPLETION_P95_MAX_SECONDS,
            "per_document_timeout_seconds": TIMEOUT_SECONDS,
        },
        "results": sorted(results, key=lambda item: item["index"]),
        "checks": checks, "passed": all(checks.values()),
    }


def write_junit(result: dict, path: Path) -> None:
    suite = Element("testsuite", name="write-ocr-qualification", tests=str(len(result["checks"])))
    failures = 0
    for name, passed in result["checks"].items():
        case = SubElement(suite, "testcase", classname="acceptance.write_ocr", name=name)
        if not passed:
            failures += 1
            failure = SubElement(case, "failure", message="Write/OCR target not met")
            failure.text = json.dumps(result, sort_keys=True)
    suite.set("failures", str(failures))
    ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    if DOCUMENTS < CONCURRENCY or CONCURRENCY < 1:
        raise SystemExit("WRITE_OCR_DOCUMENTS must be >= WRITE_OCR_CONCURRENCY >= 1")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    token = create_token()
    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(submit_and_wait, token, index) for index in range(DOCUMENTS)]
        for future in as_completed(futures):
            results.append(future.result())
    wall_seconds = time.perf_counter() - started
    result = evaluate(results, wall_seconds)
    (EVIDENCE_DIR / "write-ocr-qualification.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )
    write_junit(result, EVIDENCE_DIR / "junit-write-ocr.xml")
    print(
        "Write/OCR qualification: "
        f"{'PASS' if result['passed'] else 'FAIL'} documents={len(results)} "
        f"concurrency={CONCURRENCY} completed={sum(r['completion_status'] == 'completed' for r in results)} "
        f"submit_p95={result['submit_latency_seconds']['p95']:.3f}s "
        f"completion_p95={result['completion_latency_seconds']['p95']:.3f}s"
    )
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
