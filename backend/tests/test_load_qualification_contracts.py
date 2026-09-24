import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOAD_PATH = ROOT / "acceptance" / "tools" / "load_qualification.py"


def _module():
    spec = importlib.util.spec_from_file_location("load_qualification", LOAD_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_controlled_load_evaluation_covers_latency_errors_throughput_and_429s():
    module = _module()
    results = [
        {"endpoint": "/documents", "status": 200, "seconds": 0.05}
        for _ in range(module.REQUESTS)
    ]
    evaluation = module.evaluate_results(results, wall_seconds=2.0)

    assert evaluation["passed"] is True
    assert evaluation["requests_per_second"] == module.REQUESTS / 2.0
    assert evaluation["latency_seconds"]["p95"] == 0.05
    assert evaluation["rate_limited_count"] == 0
    assert set(evaluation["checks"]) == {
        "request_count", "error_ratio", "server_error_ratio", "p95_latency",
        "throughput", "no_unexpected_rate_limiting",
    }


def test_load_profile_is_bounded_and_clearly_not_a_capacity_claim():
    source = LOAD_PATH.read_text()

    assert 'LOAD_REQUESTS", "240"' in source
    assert 'LOAD_CONCURRENCY", "8"' in source
    assert 'LOAD_P95_MAX_SECONDS", "1.0"' in source
    assert 'LOAD_MIN_REQUESTS_PER_SECOND", "10"' in source
    assert "not a maximum-capacity claim" in source
    assert '"access_token"' in source
    assert "token" not in source.split('"load-qualification.json"', 1)[1]
