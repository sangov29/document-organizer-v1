from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_liveness_and_dependency_readiness_are_separate_contracts():
    source = (ROOT / "app" / "main.py").read_text()
    assert '@app.get("/health/live")' in source
    assert '@app.get("/health/ready")' in source
    live_fn = source.split("def liveness():", 1)[1].split(
        '@app.get("/health/ready")', 1
    )[0]
    assert "dependency_readiness" not in live_fn
    assert "HTTP_503_SERVICE_UNAVAILABLE" in source


def test_readiness_checks_required_dependencies_without_leaking_errors():
    source = (ROOT / "app" / "services" / "readiness.py").read_text()
    assert 'text("SELECT 1")' in source
    assert "rate_limiter.client.ping()" in source
    assert "storage.client.head_bucket(Bucket=storage.bucket)" in source
    assert source.count('= "unavailable"') == 3
    assert "str(exc)" not in source
    assert "repr(exc)" not in source
