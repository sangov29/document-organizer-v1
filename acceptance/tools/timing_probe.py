from __future__ import annotations

import json
import math
import os
import random
import statistics
import time
import uuid
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

import httpx

API_URL = os.getenv("ACCEPTANCE_API_URL", "http://localhost:8000/api/v1")
RUN_ID = os.getenv("ACCEPTANCE_RUN_ID", uuid.uuid4().hex[:12])
EVIDENCE_DIR = Path(os.getenv("ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER", "/evidence"))
SAMPLES = int(os.getenv("TIMING_SAMPLES", "50"))
WARMUPS = int(os.getenv("TIMING_WARMUPS", "6"))
ORDER_SEED = os.getenv("TIMING_ORDER_SEED", "acceptance-balanced-v1")
MEDIAN_TOL = float(os.getenv("TIMING_MEDIAN_REL_TOL", "0.25"))
P95_TOL = float(os.getenv("TIMING_P95_REL_TOL", "0.35"))
KS_MAX = float(os.getenv("TIMING_KS_MAX", "0.35"))
PASSWORD = "Acceptance-Timing-Synthetic!9x"


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    pos = (len(ordered) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[lower]
    fraction = pos - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def ks_statistic(a: list[float], b: list[float]) -> float:
    a_sorted, b_sorted = sorted(a), sorted(b)
    points = sorted(set(a_sorted + b_sorted))
    max_diff = 0.0
    for x in points:
        fa = sum(v <= x for v in a_sorted) / len(a_sorted)
        fb = sum(v <= x for v in b_sorted) / len(b_sorted)
        max_diff = max(max_diff, abs(fa - fb))
    return max_diff


def rel_delta(a: float, b: float) -> float:
    denom = max(min(abs(a), abs(b)), 1e-9)
    return abs(a - b) / denom


def timed(client: httpx.Client, method: str, path: str, json_body: dict) -> tuple[float, int]:
    start = time.perf_counter_ns()
    response = client.request(method, path, json=json_body)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    return elapsed_ms, response.status_code


def balanced_order(count: int, probe_name: str, phase: str) -> list[str]:
    """Build a reproducible order with equal left-first/right-first pairs."""
    if count < 2 or count % 2:
        raise ValueError("timing sample and warmup counts must be positive even numbers")
    order = ["left-first"] * (count // 2) + ["right-first"] * (count // 2)
    random.Random(f"{ORDER_SEED}:{probe_name}:{phase}").shuffle(order)
    return order


def sample_pair(client: httpx.Client, probe_name: str, left_call, right_call) -> tuple[list[float], list[float], list[int], list[int], list[str]]:
    left, right, left_status, right_status = [], [], [], []
    for first in balanced_order(WARMUPS, probe_name, "warmup"):
        if first == "left-first":
            left_call(client); right_call(client)
        else:
            right_call(client); left_call(client)
    measurement_order = balanced_order(SAMPLES, probe_name, "measurement")
    for first in measurement_order:
        if first == "left-first":
            lv, ls = left_call(client); rv, rs = right_call(client)
        else:
            rv, rs = right_call(client); lv, ls = left_call(client)
        left.append(lv); right.append(rv); left_status.append(ls); right_status.append(rs)
    return left, right, left_status, right_status, measurement_order


def summarize(name: str, left_name: str, right_name: str, left: list[float], right: list[float], statuses: tuple[list[int], list[int]], measurement_order: list[str]) -> dict:
    left_median, right_median = statistics.median(left), statistics.median(right)
    left_p95, right_p95 = percentile(left, 0.95), percentile(right, 0.95)
    median_delta = rel_delta(left_median, right_median)
    p95_delta = rel_delta(left_p95, right_p95)
    ks = ks_statistic(left, right)
    passed = median_delta <= MEDIAN_TOL and p95_delta <= P95_TOL and ks <= KS_MAX
    return {
        "probe": name,
        "groups": {
            left_name: {"raw_ms": left, "median_ms": left_median, "p95_ms": left_p95, "statuses": statuses[0]},
            right_name: {"raw_ms": right, "median_ms": right_median, "p95_ms": right_p95, "statuses": statuses[1]},
        },
        "comparison": {
            "median_relative_delta": median_delta,
            "p95_relative_delta": p95_delta,
            "ks_statistic": ks,
        },
        "measurement_order": measurement_order,
        "tolerance": {
            "median_relative_delta_max": MEDIAN_TOL,
            "p95_relative_delta_max": P95_TOL,
            "ks_statistic_max": KS_MAX,
            "classification": "local harness regression guard; not a product NFR benchmark",
        },
        "passed": passed,
    }


def write_junit(results: list[dict], path: Path) -> None:
    suite = Element("testsuite", name="UM anti-enumeration timing", tests=str(len(results)))
    failures = 0
    for result in results:
        case = SubElement(suite, "testcase", classname="acceptance.timing", name=result["probe"])
        props = SubElement(case, "properties")
        for key, value in result["comparison"].items():
            SubElement(props, "property", name=key, value=f"{value:.6f}")
        if not result["passed"]:
            failures += 1
            failure = SubElement(case, "failure", message="Timing distributions exceeded local harness tolerance")
            failure.text = json.dumps({"comparison": result["comparison"], "tolerance": result["tolerance"]}, sort_keys=True)
    suite.set("failures", str(failures))
    ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    existing_email = f"acceptance+{RUN_ID}-timing-existing@example.com"

    with httpx.Client(base_url=API_URL, timeout=30.0) as client:
        # Establish one existing account through the public API. Verification is
        # unnecessary for these probes because each measured endpoint reaches
        # the relevant password/request branch before verification matters.
        setup = client.post("/auth/register", json={"email": existing_email, "password": PASSWORD})
        if setup.status_code != 202:
            raise SystemExit(f"timing setup registration failed with status {setup.status_code}")

        counter = 0
        def reg_new(c):
            nonlocal counter
            counter += 1
            email = f"acceptance+{RUN_ID}-timing-new-{counter:04d}@example.com"
            return timed(c, "POST", "/auth/register", {"email": email, "password": PASSWORD})

        def reg_existing(c):
            return timed(c, "POST", "/auth/register", {"email": existing_email, "password": PASSWORD})

        def login_existing_wrong(c):
            return timed(c, "POST", "/auth/login", {"email": existing_email, "password": "Acceptance-Wrong-Password!8z"})

        def login_missing(c):
            return timed(c, "POST", "/auth/login", {"email": f"missing-{RUN_ID}@example.com", "password": "Acceptance-Wrong-Password!8z"})

        def reset_existing(c):
            return timed(c, "POST", "/auth/password-reset/request", {"email": existing_email})

        def reset_missing(c):
            return timed(c, "POST", "/auth/password-reset/request", {"email": f"missing-reset-{RUN_ID}@example.com"})

        results = []
        for name, left_name, right_name, left_call, right_call in [
            ("registration_existing_vs_new", "existing", "new", reg_existing, reg_new),
            ("login_existing_wrong_password_vs_nonexistent", "existing_wrong_password", "nonexistent", login_existing_wrong, login_missing),
            ("password_reset_existing_vs_nonexistent", "existing", "nonexistent", reset_existing, reset_missing),
        ]:
            left, right, ls, rs, order = sample_pair(client, name, left_call, right_call)
            results.append(summarize(name, left_name, right_name, left, right, (ls, rs), order))

    document = {
        "run_id": RUN_ID,
        "sample_count_per_group": SAMPLES,
        "warmups_per_group": WARMUPS,
        "measurement_order_method": "seeded balanced random branch-first order within pairs",
        "measurement_order_seed": ORDER_SEED,
        "functional_results": "separate; see junit-functional.xml",
        "results": results,
    }
    (EVIDENCE_DIR / "timing.json").write_text(json.dumps(document, indent=2, sort_keys=True))
    write_junit(results, EVIDENCE_DIR / "junit-timing.xml")

    print("Timing evidence (separate from functional pass/fail):")
    for result in results:
        comp = result["comparison"]
        print(
            f"  {result['probe']}: {'PASS' if result['passed'] else 'FAIL'} "
            f"median_delta={comp['median_relative_delta']:.3f} "
            f"p95_delta={comp['p95_relative_delta']:.3f} ks={comp['ks_statistic']:.3f}"
        )
    return 0 if all(r["passed"] for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
