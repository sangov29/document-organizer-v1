from __future__ import annotations

import time

import pyotp
import pytest

from conftest import (
    db_user_state,
    extract_token_from_mail,
    login,
    wait_for_mail_text,
 )


def _stable_totp(secret: str) -> str:
    # Avoid generating a code in the final seconds of a 30-second TOTP window.
    while int(time.time()) % 30 > 22:
        time.sleep(0.5)
    return pyotp.TOTP(secret).now()


@pytest.mark.catalogue("UM-TC-001", steps="1-9")
def test_UM_TC_001_registration_verification(api, evidence, email_factory, password_factory):
    malformed = api.request(
        "POST", "/auth/register", label="UM-TC-001 malformed email",
        json={"email": "not-an-email", "password": password_factory("malformed")},
    )
    assert malformed.status_code == 422

    email = email_factory("um001")
    password = password_factory("um001")
    registered = api.request(
        "POST", "/auth/register", label="UM-TC-001 register new",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 202
    response_snapshot = registered.json()

    state_before = db_user_state(email)
    evidence.note("verification-state-before", {"is_verified": state_before["is_verified"] if state_before else None})
    assert state_before and state_before["is_verified"] is False
    assert state_before["password_is_plaintext"] is False
    evidence.note("password-storage", {"password_scheme": state_before["password_scheme"], "recoverable_plaintext": False})

    before_verify = login(api, email, password, label="UM-TC-001 login before verification")
    assert before_verify.status_code == 401

    mail = wait_for_mail_text(email, subject_phrase="Verify")
    evidence.note("mail-sink", {"kind": "verification", "received": True, "provider_claim": False})
    token = extract_token_from_mail(mail, "/verify-email")
    verified = api.request(
        "POST", "/auth/verify-email", label="UM-TC-001 verify email", json={"token": token}
    )
    assert verified.status_code == 200
    assert verified.json()["is_verified"] is True

    after_verify = login(api, email, password, label="UM-TC-001 login after verification")
    assert after_verify.status_code == 200

    existing = api.request(
        "POST", "/auth/register", label="UM-TC-001 register existing",
        json={"email": email, "password": password_factory("existing")},
    )
    assert existing.status_code == registered.status_code
    assert existing.json() == response_snapshot
    evidence.note("anti-enumeration-functional", {"status_equal": True, "body_equal": True, "timing": "see timing.json"})


@pytest.mark.catalogue("UM-TC-002", steps="1-4,6-partial")
def test_UM_TC_002_login_and_list_isolation(api, evidence, email_factory, password_factory):
    # Create two verified accounts through the public API.
    accounts = []
    for label in ("uma", "umb"):
        email = email_factory(label)
        password = password_factory(label)
        reg = api.request("POST", "/auth/register", label=f"UM-TC-002 register {label}", json={"email": email, "password": password})
        assert reg.status_code == 202
        token = extract_token_from_mail(wait_for_mail_text(email, subject_phrase="Verify"), "/verify-email")
        verify = api.request("POST", "/auth/verify-email", label=f"UM-TC-002 verify {label}", json={"token": token})
        assert verify.status_code == 200
        accounts.append({"email": email, "password": password})

    a, b = accounts
    login_a = login(api, a["email"], a["password"], label="UM-TC-002 login A")
    assert login_a.status_code == 200
    jwt_a = login_a.json()["access_token"]

    wrong = login(api, a["email"], password_factory("wrong"), label="UM-TC-002 wrong password")
    missing = login(api, email_factory("missing"), password_factory("wrong"), label="UM-TC-002 nonexistent email")
    assert wrong.status_code == 401 and missing.status_code == 401
    assert wrong.json() == missing.json()

    login_b = login(api, b["email"], b["password"], label="UM-TC-002 login B")
    assert login_b.status_code == 200
    jwt_b = login_b.json()["access_token"]

    # Create one resource for B; A must not see it through the public list API.
    from fixtures import png_bytes
    body = png_bytes("isolation", b["email"])
    upload_b = api.request(
        "POST", "/documents", label="UM-TC-002 B upload", token=jwt_b,
        files={"file": ("b-private.png", body, "image/png")},
    )
    assert upload_b.status_code == 202
    private_id = upload_b.json()["id"]
    evidence.document(private_id)

    list_a = api.request("GET", "/documents", label="UM-TC-002 A list", token=jwt_a)
    assert list_a.status_code == 200
    assert private_id not in {item["id"] for item in list_a.json()}
    serialized = str(list_a.json())
    assert b["email"] not in serialized


@pytest.mark.catalogue("UM-TC-002", steps="5-6")
@pytest.mark.known_gap
@pytest.mark.xfail(strict=True, reason="No public resource-by-ID endpoint exists yet; direct identifier tampering cannot be exercised without inventing a test-only API")
def test_UM_TC_002_direct_resource_identifier_isolation_known_gap():
    pytest.fail("UM-TC-002 steps 5-6 require a public resource-by-ID API before this substep can execute")


@pytest.mark.catalogue("UM-TC-003", steps="1-7 + JWT revocation")
def test_UM_TC_003_password_reset_lifecycle(api, evidence, verified_account, email_factory, password_factory):
    old_password = verified_account["password"]
    email = verified_account["email"]

    login_before = login(api, email, old_password, label="UM-TC-003 login before reset")
    assert login_before.status_code == 200
    pre_reset_jwt = login_before.json()["access_token"]

    req_existing = api.request("POST", "/auth/password-reset/request", label="UM-TC-003 reset existing", json={"email": email})
    req_missing = api.request("POST", "/auth/password-reset/request", label="UM-TC-003 reset missing", json={"email": email_factory("reset-missing")})
    assert req_existing.status_code == req_missing.status_code == 202
    assert req_existing.json() == req_missing.json()
    evidence.note("reset-enumeration-functional", {"status_equal": True, "body_equal": True, "timing": "see timing.json"})

    mail = wait_for_mail_text(email, subject_phrase="Reset")
    evidence.note("mail-sink", {"kind": "password-reset", "received": True, "provider_claim": False})
    token = extract_token_from_mail(mail, "/reset-password")
    new_password = password_factory("reset-new")
    confirmed = api.request(
        "POST", "/auth/password-reset/confirm", label="UM-TC-003 confirm reset",
        json={"token": token, "new_password": new_password},
    )
    assert confirmed.status_code == 200

    reused = api.request(
        "POST", "/auth/password-reset/confirm", label="UM-TC-003 reuse reset token",
        json={"token": token, "new_password": password_factory("reuse")},
    )
    assert reused.status_code == 400

    old_login = login(api, email, old_password, label="UM-TC-003 old password rejected")
    new_login = login(api, email, new_password, label="UM-TC-003 new password accepted")
    assert old_login.status_code == 401
    assert new_login.status_code == 200

    # Explicit user requirement: replay a JWT issued before reset.
    replay = api.request("GET", "/documents", label="UM-TC-003 replay pre-reset JWT", token=pre_reset_jwt)
    assert replay.status_code == 401


@pytest.mark.catalogue("UM-TC-003", steps="8")
def test_UM_TC_003_password_reset_expiry(api, evidence, verified_account, password_factory):
    email = verified_account["email"]
    req = api.request("POST", "/auth/password-reset/request", label="UM-TC-003 request expiring token", json={"email": email})
    assert req.status_code == 202
    token = extract_token_from_mail(wait_for_mail_text(email, subject_phrase="Reset"), "/reset-password")
    evidence.note("expiry-wait", {"configured_minutes": 1, "sleep_seconds": 65})
    time.sleep(65)
    expired = api.request(
        "POST", "/auth/password-reset/confirm", label="UM-TC-003 expired reset token",
        json={"token": token, "new_password": password_factory("expired")},
    )
    assert expired.status_code == 400


@pytest.mark.catalogue("UM-TC-004", steps="1-6")
def test_UM_TC_004_logout_and_idle_expiry(api, evidence, verified_account):
    email, password = verified_account["email"], verified_account["password"]
    logged_in = login(api, email, password, label="UM-TC-004 initial login")
    assert logged_in.status_code == 200
    old_jwt = logged_in.json()["access_token"]

    before = api.request("GET", "/documents", label="UM-TC-004 authenticated access", token=old_jwt)
    assert before.status_code == 200
    logout = api.request("POST", "/auth/logout", label="UM-TC-004 logout", token=old_jwt)
    assert logout.status_code == 200
    replay = api.request("GET", "/documents", label="UM-TC-004 replay logged-out JWT", token=old_jwt)
    assert replay.status_code == 401

    login_again = login(api, email, password, label="UM-TC-004 login again")
    assert login_again.status_code == 200
    idle_jwt = login_again.json()["access_token"]
    evidence.note("idle-expiry", {"configured_minutes": 1, "sleep_seconds": 65})
    time.sleep(65)
    after_idle = api.request("GET", "/documents", label="UM-TC-004 post-idle JWT replay", token=idle_jwt)
    assert after_idle.status_code == 401


@pytest.mark.catalogue("UM-TC-005", steps="1-7")
def test_UM_TC_005_totp_optional_then_mandatory(api, evidence, verified_account):
    email, password = verified_account["email"], verified_account["password"]
    initial = login(api, email, password, label="UM-TC-005 login MFA disabled")
    assert initial.status_code == 200
    jwt_initial = initial.json()["access_token"]

    setup = api.request("POST", "/auth/totp/setup", label="UM-TC-005 setup TOTP", token=jwt_initial)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    evidence.note("totp-setup", {"secret_returned_to_authenticated_enrollment_flow": True, "secret_value": "<redacted>"})

    # Required by the user: setup alone must not make MFA mandatory.
    preconfirm = login(api, email, password, label="UM-TC-005 login after setup before confirmation")
    assert preconfirm.status_code == 200
    jwt_preconfirm = preconfirm.json()["access_token"]

    valid_code = _stable_totp(secret)
    confirmed = api.request(
        "POST", "/auth/totp/confirm", label="UM-TC-005 confirm TOTP", token=jwt_preconfirm,
        json={"code": valid_code},
    )
    assert confirmed.status_code == 200 and confirmed.json()["totp_enabled"] is True

    password_only = login(api, email, password, label="UM-TC-005 password-only after confirmation")
    login_code = _stable_totp(secret)
    invalid_code = f"{(int(login_code) + 1) % 1_000_000:06d}"
    invalid_totp = login(api, email, password, label="UM-TC-005 invalid TOTP", totp_code=invalid_code)
    valid_totp = login(api, email, password, label="UM-TC-005 valid TOTP", totp_code=login_code)
    assert password_only.status_code == 401
    assert invalid_totp.status_code == 401
    assert valid_totp.status_code == 200
    jwt_mfa = valid_totp.json()["access_token"]

    disabled = api.request(
        "POST", "/auth/totp/disable", label="UM-TC-005 disable TOTP", token=jwt_mfa,
        json={"code": _stable_totp(secret)},
    )
    assert disabled.status_code == 200 and disabled.json()["totp_enabled"] is False

    after_disable = login(api, email, password, label="UM-TC-005 login after disable")
    assert after_disable.status_code == 200
