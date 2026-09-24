import time

import pyotp

from conftest import extract_token_from_mail, login, wait_for_mail_text


def test_operational_liveness_and_readiness(api, evidence):
    live = api.client.get("http://localhost:8000/health/live")
    evidence.response("operational liveness", live)
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert live.headers["X-Content-Type-Options"] == "nosniff"
    assert live.headers["X-Frame-Options"] == "DENY"
    assert live.headers["Referrer-Policy"] == "no-referrer"
    assert live.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"

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


def test_operational_totp_rate_limit_threshold_isolation_and_recovery(
    api, evidence, auth_token, email_factory, password_factory
):
    setup_a = api.request(
        "POST", "/auth/totp/setup", label="rate-limit setup account A", token=auth_token
    )
    assert setup_a.status_code == 200
    valid_a = pyotp.TOTP(setup_a.json()["secret"]).now()
    invalid_a = f"{(int(valid_a) + 1) % 1_000_000:06d}"

    for attempt in range(3):
        rejected = api.request(
            "POST", "/auth/totp/confirm", label=f"TOTP under limit #{attempt + 1}",
            token=auth_token, json={"code": invalid_a},
        )
        assert rejected.status_code == 400

    throttled = api.request(
        "POST", "/auth/totp/confirm", label="TOTP over limit",
        token=auth_token, json={"code": invalid_a},
    )
    assert throttled.status_code == 429
    assert throttled.headers["Retry-After"] == "2"

    email_b = email_factory("totp-rate-isolation")
    password_b = password_factory("totp-rate-isolation")
    assert api.request(
        "POST", "/auth/register", label="rate-limit register account B",
        json={"email": email_b, "password": password_b},
    ).status_code == 202
    token_b = extract_token_from_mail(
        wait_for_mail_text(email_b, subject_phrase="Verify"), "/verify-email"
    )
    assert api.request(
        "POST", "/auth/verify-email", label="rate-limit verify account B",
        json={"token": token_b},
    ).status_code == 200
    login_b = login(api, email_b, password_b, label="rate-limit login account B")
    assert login_b.status_code == 200
    jwt_b = login_b.json()["access_token"]
    setup_b = api.request(
        "POST", "/auth/totp/setup", label="rate-limit setup account B", token=jwt_b
    )
    assert setup_b.status_code == 200
    valid_b = pyotp.TOTP(setup_b.json()["secret"]).now()
    invalid_b = f"{(int(valid_b) + 1) % 1_000_000:06d}"
    isolated = api.request(
        "POST", "/auth/totp/confirm", label="different account unaffected",
        token=jwt_b, json={"code": invalid_b},
    )
    assert isolated.status_code == 400

    time.sleep(2.5)
    current_a = pyotp.TOTP(setup_a.json()["secret"]).now()
    invalid_after_recovery = f"{(int(current_a) + 1) % 1_000_000:06d}"
    recovered = api.request(
        "POST", "/auth/totp/confirm", label="TOTP after window recovery",
        token=auth_token, json={"code": invalid_after_recovery},
    )
    assert recovered.status_code == 400
    evidence.note("totp-rate-limiting", {
        "threshold_enforced": True,
        "subject_isolation_confirmed": True,
        "window_recovery_confirmed": True,
        "retry_after_seconds": 2,
    })
