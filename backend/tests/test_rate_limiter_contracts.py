from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_auth_rate_limits_use_hashed_redis_keys_and_atomic_expiry():
    limiter = (ROOT / "backend/app/services/rate_limiter.py").read_text()
    auth = (ROOT / "backend/app/api/auth.py").read_text()

    assert "hashlib.sha256" in limiter
    assert "redis.call('INCR'" in limiter
    assert "redis.call('EXPIRE'" in limiter
    assert 'rate_limiter.allowed("login", email' in auth
    assert 'rate_limiter.allowed("totp-confirm", subject' in auth
    assert 'status_code=429' in auth
    assert 'headers={"Retry-After"' in auth


def test_success_clears_failed_attempt_budget_and_acceptance_override_is_explicit():
    auth = (ROOT / "backend/app/api/auth.py").read_text()
    compose = (ROOT / "acceptance/docker-compose.acceptance.yml").read_text()

    assert 'rate_limiter.clear("login", email)' in auth
    assert 'rate_limiter.clear("totp-confirm", subject)' in auth
    assert 'LOGIN_RATE_LIMIT: "1000"' in compose
    assert "timing probe intentionally performs 212 failed logins" in compose
    assert 'TOTP_RATE_LIMIT: "3"' in compose
    assert 'TOTP_RATE_WINDOW_SECONDS: "2"' in compose
