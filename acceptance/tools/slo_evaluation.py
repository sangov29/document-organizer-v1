from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement


ROOT_URL = os.getenv("ACCEPTANCE_ROOT_URL", "http://localhost:8000").rstrip("/")
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")
EVIDENCE_DIR = Path(os.getenv("ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER", "/evidence"))
MIN_REQUESTS = int(os.getenv("SLO_MIN_API_REQUESTS", "100"))
MAX_5XX_RATIO = float(os.getenv("SLO_MAX_5XX_RATIO", "0.01"))
P95_LATENCY_SECONDS = float(os.getenv("SLO_P95_LATENCY_SECONDS", "2.5"))

METRIC_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\{(?P<labels>.*)\} "
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)$"
)
LABEL_RE = re.compile(r'(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:\\.|[^"])*)"')


def _labels(raw: str) -> dict[str, str]:
    values = {}
    for match in LABEL_RE.finditer(raw):
        value = match.group("value")
        values[match.group("name")] = (
            value.replace(r"\n", "\n").replace(r'\"', '"').replace(r"\\", "\\")
        )
    return values


def parse_metrics(payload: str) -> list[tuple[str, dict[str, str], float]]:
    samples = []
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        match = METRIC_RE.match(line)
        if match:
            samples.append(
                (match.group("name"), _labels(match.group("labels")), float(match.group("value")))
            )
    return samples


def evaluate_metrics(payload: str) -> dict:
    request_count = 0
    server_error_count = 0
    successful_count = 0
    successful_buckets: dict[float, int] = {}

    for name, labels, value in parse_metrics(payload):
        route = labels.get("route", "")
        if not route.startswith("/api/v1/"):
            continue
        status_class = labels.get("status_class")
        if name == "document_http_requests_total":
            count = int(value)
            request_count += count
            if status_class == "5xx":
                server_error_count += count
            if status_class == "2xx":
                successful_count += count
        elif name == "document_http_request_duration_seconds_bucket" and status_class == "2xx":
            bound = labels.get("le")
            if bound and bound != "+Inf":
                numeric_bound = float(bound)
                successful_buckets[numeric_bound] = successful_buckets.get(numeric_bound, 0) + int(value)

    error_ratio = server_error_count / request_count if request_count else 1.0
    rank = math.ceil(successful_count * 0.95)
    p95_upper_bound = None
    for bound in sorted(successful_buckets):
        if successful_buckets[bound] >= rank:
            p95_upper_bound = bound
            break

    checks = {
        "traffic_sample": request_count >= MIN_REQUESTS,
        "availability": error_ratio <= MAX_5XX_RATIO,
        "latency": (
            successful_count > 0
            and p95_upper_bound is not None
            and p95_upper_bound <= P95_LATENCY_SECONDS
        ),
    }
    return {
        "scope": "synthetic acceptance traffic; not a production SLO claim",
        "request_count": request_count,
        "successful_request_count": successful_count,
        "server_error_count": server_error_count,
        "server_error_ratio": error_ratio,
        "successful_request_p95_upper_bound_seconds": p95_upper_bound,
        "targets": {
            "minimum_api_requests": MIN_REQUESTS,
            "maximum_5xx_ratio": MAX_5XX_RATIO,
            "successful_request_p95_seconds": P95_LATENCY_SECONDS,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def _get(path: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    request = urllib.request.Request(f"{ROOT_URL}{path}", headers=headers or {})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode()


def write_junit(result: dict, path: Path) -> None:
    suite = Element("testsuite", name="operational-slo-evaluation", tests="4")
    failures = 0
    cases = {
        "dependency_readiness": result["readiness_passed"],
        "minimum_traffic_sample": result["checks"]["traffic_sample"],
        "api_5xx_ratio": result["checks"]["availability"],
        "successful_request_p95_latency": result["checks"]["latency"],
    }
    for name, passed in cases.items():
        case = SubElement(suite, "testcase", classname="acceptance.slo", name=name)
        if not passed:
            failures += 1
            failure = SubElement(case, "failure", message="Acceptance SLO target not met")
            failure.text = json.dumps(result, sort_keys=True, allow_nan=False)
    suite.set("failures", str(failures))
    ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    if not METRICS_TOKEN:
        raise SystemExit("METRICS_TOKEN must be configured for SLO evaluation")

    ready_status, ready_body = _get("/health/ready")
    readiness = json.loads(ready_body)
    metrics_status, metrics_body = _get(
        "/internal/metrics", {"X-Metrics-Token": METRICS_TOKEN}
    )
    result = evaluate_metrics(metrics_body)
    result.update(
        {
            "readiness_passed": ready_status == 200 and readiness.get("status") == "ready",
            "readiness": readiness,
            "metrics_status": metrics_status,
        }
    )
    result["passed"] = result["passed"] and result["readiness_passed"] and metrics_status == 200

    (EVIDENCE_DIR / "slo-evaluation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    )
    write_junit(result, EVIDENCE_DIR / "junit-slo.xml")
    print(
        "Acceptance SLO evaluation: "
        f"{'PASS' if result['passed'] else 'FAIL'} requests={result['request_count']} "
        f"5xx_ratio={result['server_error_ratio']:.4f} "
        f"p95_upper_bound={result['successful_request_p95_upper_bound_seconds']}s"
    )
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
