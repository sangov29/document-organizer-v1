from app.services.http_metrics import HttpMetrics


def test_bounded_histogram_counts_are_cumulative_and_no_raw_identifiers():
    metrics = HttpMetrics()
    metrics.observe("/documents/{document_id}", 200, 0.075)
    metrics.observe("/documents/{document_id}", 204, 11.0)
    payload = metrics.render()
    labels = 'route="/documents/{document_id}",status_class="2xx"'
    assert f"document_http_requests_total{{{labels}}} 2" in payload
    assert f'document_http_request_duration_seconds_bucket{{{labels},le="0.05"}} 0' in payload
    assert f'document_http_request_duration_seconds_bucket{{{labels},le="0.1"}} 1' in payload
    assert f'document_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} 2' in payload
    assert f"document_http_request_duration_seconds_count{{{labels}}} 2" in payload


def test_metrics_endpoint_requires_configured_token_and_uses_route_templates():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "main.py").read_text()
    assert "secrets.compare_digest(x_metrics_token, token)" in source
    assert "if not token or not x_metrics_token" in source
    assert "include_in_schema=False" in source
    telemetry = (root / "app" / "services" / "http_metrics.py").read_text()
    assert 'request.scope.get("route")' in telemetry
    assert 'or "_unmatched"' in telemetry
    assert "request.url.path as" not in telemetry
