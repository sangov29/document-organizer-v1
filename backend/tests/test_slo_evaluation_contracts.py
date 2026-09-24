import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SLO_PATH = ROOT / "acceptance" / "tools" / "slo_evaluation.py"


def _module():
    spec = importlib.util.spec_from_file_location("slo_evaluation", SLO_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_slo_evaluation_aggregates_api_metrics_and_excludes_health_traffic():
    module = _module()
    payload = """
document_http_requests_total{route="/api/v1/documents",status_class="2xx"} 199
document_http_requests_total{route="/api/v1/documents",status_class="5xx"} 1
document_http_requests_total{route="/health/live",status_class="5xx"} 50
document_http_request_duration_seconds_bucket{route="/api/v1/documents",status_class="2xx",le="0.5"} 180
document_http_request_duration_seconds_bucket{route="/api/v1/documents",status_class="2xx",le="1"} 190
document_http_request_duration_seconds_bucket{route="/api/v1/documents",status_class="2xx",le="2.5"} 199
document_http_request_duration_seconds_bucket{route="/api/v1/documents",status_class="2xx",le="+Inf"} 199
"""
    result = module.evaluate_metrics(payload)

    assert result["request_count"] == 200
    assert result["server_error_ratio"] == 0.005
    assert result["successful_request_p95_upper_bound_seconds"] == 1.0
    assert result["passed"] is True


def test_slo_thresholds_are_explicit_and_do_not_claim_production_proof():
    source = SLO_PATH.read_text()

    assert 'SLO_MIN_API_REQUESTS", "100"' in source
    assert 'SLO_MAX_5XX_RATIO", "0.01"' in source
    assert 'SLO_P95_LATENCY_SECONDS", "2.5"' in source
    assert "not a production SLO claim" in source
