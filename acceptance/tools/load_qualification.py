from __future__ import annotations

import json
import os
import re
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

API_URL = os.getenv("ACCEPTANCE_API_URL", "http://localhost:8000/api/v1")
MAILPIT_URL = os.getenv("MAILPIT_API_URL", "http://mailpit:8025")
RUN_ID = os.getenv("ACCEPTANCE_RUN_ID", uuid.uuid4().hex[:12])
EVIDENCE_DIR = Path(os.getenv("ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER", "/evidence"))
REQUESTS = int(os.getenv("LOAD_REQUESTS", "240"))
CONCURRENCY = int(os.getenv("LOAD_CONCURRENCY", "8"))
P95_MAX_SECONDS = float(os.getenv("LOAD_P95_MAX_SECONDS", "1.0"))
MIN_REQUESTS_PER_SECOND = float(os.getenv("LOAD_MIN_REQUESTS_PER_SECOND", "10"))
MAX_ERROR_RATIO = float(os.getenv("LOAD_MAX_ERROR_RATIO", "0.01"))
MAX_5XX_RATIO = float(os.getenv("LOAD_MAX_5XX_RATIO", "0.01"))
PASSWORD = "Acceptance-Load-Synthetic!9x"

_thread_state = threading.local()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def evaluate_results(results: list[dict], wall_seconds: float) -> dict:
    latencies = [item["seconds"] for item in results]
    total = len(results)
    errors = sum(item["status"] < 200 or item["status"] >= 300 for item in results)
    server_errors = sum(item["status"] >= 500 for item in results)
    rate_limited = sum(item["status"] == 429 for item in results)
    throughput = total / wall_seconds if wall_seconds > 0 else 0.0
    p95 = percentile(latencies, 0.95)
    statuses: dict[str, int] = {}
    endpoints: dict[str, int] = {}
    for item in results:
        status = str(item["status"])
        statuses[status] = statuses.get(status, 0) + 1
        endpoints[item["endpoint"]] = endpoints.get(item["endpoint"], 0) + 1

    checks = {
        "request_count": total == REQUESTS,
        "error_ratio": total > 0 and errors / total <= MAX_ERROR_RATIO,
        "server_error_ratio": total > 0 and server_errors / total <= MAX_5XX_RATIO,
        "p95_latency": p95 <= P95_MAX_SECONDS,
        "throughput": throughput >= MIN_REQUESTS_PER_SECOND,
        "no_unexpected_rate_limiting": rate_limited == 0,
    }
    return {
        "scope": "controlled synthetic authenticated read load; not a maximum-capacity claim",
        "request_count": total,
        "concurrency": CONCURRENCY,
        "wall_seconds": wall_seconds,
        "requests_per_second": throughput,
        "latency_seconds": {
            "median": statistics.median(latencies) if latencies else 0.0,
            "p95": p95,
            "maximum": max(latencies) if latencies else 0.0,
        },
        "error_count": errors,
        "server_error_count": server_errors,
        "rate_limited_count": rate_limited,
        "status_counts": statuses,
        "endpoint_counts": endpoints,
        "targets": {
            "requests": REQUESTS,
            "concurrency": CONCURRENCY,
            "maximum_error_ratio": MAX_ERROR_RATIO,
            "maximum_5xx_ratio": MAX_5XX_RATIO,
            "maximum_p95_seconds": P95_MAX_SECONDS,
            "minimum_requests_per_second": MIN_REQUESTS_PER_SECOND,
            "maximum_unexpected_429": 0,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def wait_for_verification_token(email: str, timeout: float = 30.0) -> str:
    import httpx

    deadline = time.time() + timeout
    query = f'to:"{email}" subject:"Verify"'
    with httpx.Client(base_url=MAILPIT_URL, timeout=5.0) as client:
        while time.time() < deadline:
            response = client.get("/view/latest.txt", params={"query": query})
            if response.status_code == 200:
                match = re.search(r"/verify-email\?token=([^\s]+)", response.text)
                if match:
                    return match.group(1).strip()
            time.sleep(0.5)
    raise RuntimeError("verification message was not received by the local mail sink")


def create_token() -> str:
    import httpx

    email = f"acceptance+{RUN_ID}-load-{uuid.uuid4().hex[:8]}@example.com"
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


def _request(token: str, index: int) -> dict:
    import httpx

    client = getattr(_thread_state, "client", None)
    if client is None:
        client = httpx.Client(
            base_url=API_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {token}"},
        )
        _thread_state.client = client
    endpoint = "/documents" if index % 4 else "/documents/search?page_size=20"
    started = time.perf_counter()
    try:
        response = client.get(endpoint)
        status = response.status_code
    except httpx.HTTPError:
        status = 599
    return {
        "endpoint": endpoint.split("?", 1)[0],
        "status": status,
        "seconds": time.perf_counter() - started,
    }


def write_junit(result: dict, path: Path) -> None:
    suite = Element("testsuite", name="controlled-load-qualification", tests=str(len(result["checks"])))
    failures = 0
    for name, passed in result["checks"].items():
        case = SubElement(suite, "testcase", classname="acceptance.load", name=name)
        if not passed:
            failures += 1
            failure = SubElement(case, "failure", message="Controlled load target not met")
            failure.text = json.dumps(result, sort_keys=True)
    suite.set("failures", str(failures))
    ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    if REQUESTS < CONCURRENCY or CONCURRENCY < 1:
        raise SystemExit("LOAD_REQUESTS must be >= LOAD_CONCURRENCY >= 1")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    token = create_token()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        results = list(executor.map(lambda index: _request(token, index), range(REQUESTS)))
    wall_seconds = time.perf_counter() - started
    evaluation = evaluate_results(results, wall_seconds)
    (EVIDENCE_DIR / "load-qualification.json").write_text(
        json.dumps(evaluation, indent=2, sort_keys=True)
    )
    write_junit(evaluation, EVIDENCE_DIR / "junit-load.xml")
    print(
        "Controlled load qualification: "
        f"{'PASS' if evaluation['passed'] else 'FAIL'} "
        f"requests={evaluation['request_count']} concurrency={CONCURRENCY} "
        f"rps={evaluation['requests_per_second']:.2f} "
        f"p95={evaluation['latency_seconds']['p95']:.3f}s "
        f"errors={evaluation['error_count']} rate_limited={evaluation['rate_limited_count']}"
    )
    return 0 if evaluation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
