def test_operational_liveness_and_readiness(api, evidence):
    live = api.client.get("http://localhost:8000/health/live")
    evidence.response("operational liveness", live)
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}

    ready = api.client.get("http://localhost:8000/health/ready")
    evidence.response("operational dependency readiness", ready)
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "dependencies": {
            "postgres": "ok",
            "redis": "ok",
            "object_storage": "ok",
        },
    }


def test_operational_metrics_are_private_and_do_not_include_request_data(api, evidence):
    marker = "request-private-identifier-489213"
    secret = "acceptance-metrics-probe-only"
    live = api.client.get(f"http://localhost:8000/health/live?source={marker}")
    assert live.status_code == 200

    missing = api.client.get("http://localhost:8000/internal/metrics")
    wrong = api.client.get("http://localhost:8000/internal/metrics", headers={"X-Metrics-Token": "wrong"})
    assert missing.status_code == wrong.status_code == 404
    assert missing.json() == wrong.json()

    metrics = api.client.get("http://localhost:8000/internal/metrics", headers={"X-Metrics-Token": secret})
    assert metrics.status_code == 200
    assert "document_http_requests_total" in metrics.text
    assert "document_http_request_duration_seconds_bucket" in metrics.text
    assert 'route="/health/live"' in metrics.text
    assert marker not in metrics.text
    assert secret not in metrics.text
    assert 'route="/internal/metrics"' not in metrics.text
    evidence.note("private-operational-metrics", {"denied_without_token": True,
                                                  "no_request_data": True})
