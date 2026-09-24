from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backend_applies_baseline_security_headers_to_all_responses():
    source = (ROOT / "backend" / "app" / "main.py").read_text()

    assert 'response.headers.setdefault("X-Content-Type-Options", "nosniff")' in source
    assert 'response.headers.setdefault("X-Frame-Options", "DENY")' in source
    assert 'response.headers.setdefault("Referrer-Policy", "no-referrer")' in source
    assert '"Permissions-Policy", "camera=(), microphone=(), geolocation=()"' in source


def test_frontend_applies_matching_baseline_security_headers():
    source = (ROOT / "frontend" / "next.config.mjs").read_text()

    assert "{key: 'X-Content-Type-Options', value: 'nosniff'}" in source
    assert "{key: 'X-Frame-Options', value: 'DENY'}" in source
    assert "{key: 'Referrer-Policy', value: 'no-referrer'}" in source
    assert "{key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()'}" in source
