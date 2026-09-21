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
