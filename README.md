# Intelligent Personal Document Organizer — V1

Implementation repository based on Architecture Baseline v0.1 and frozen Test Catalogue v0.5.

## Sprint 1 status

The repository now implements the UM + DI application paths needed to begin running the existing catalogue tests rather than writing more specification.

### Authentication / user management

- registration with generic anti-enumerating external response
- equalized Argon2 work for new/existing registration branches
- login with a process-level dummy password hash for unknown accounts
- one-time expiring email verification using a versioned signed token
- Redis-backed server-side login sessions with idle-TTL refresh
- logout that revokes the active server-side session
- password-reset request that never queries account existence in the request path and always queues the same async task
- one-time expiring password-reset token using `reset_version`
- reset replaces the password hash and invalidates active server-side sessions
- optional TOTP setup/confirm/disable
- TOTP shared secret encrypted at rest with Fernet and only activated after successful code confirmation

### Document ingestion

- PDF/JPG/PNG upload
- SHA-256 exact-duplicate detection
- configurable upload limit
- immutable UUID-based object-storage keys
- ProcessingJob + correlation ID
- idempotent worker-side multi-page PDF splitting into immutable page objects + `Page` rows
- JPG/PNG single-page persistence
- bulk upload with per-file transaction/error boundaries
- partial batch failures do not block successful sibling uploads
- explicit failed state if queue handoff fails after durable ingestion

## Migrations

Current Alembic chain:

```text
0001_initial_domain_model
  -> 0002_email_verification
  -> 0003_password_reset_totp
```

`0003` adds `User.reset_version` and `User.totp_secret_ciphertext` without adding a thirteenth domain entity.

## Required local configuration

```bash
cp .env.example .env
```

Generate the TOTP encryption key before starting the backend:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the output as `TOTP_FERNET_KEY` in `.env`.

Then run:

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

Open:
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Password-reset behavior

`POST /api/v1/auth/password-reset/request` deliberately does not query the account database. It always queues `send_password_reset_email` and returns the same 202 response. The worker decides whether to send or no-op, keeping account-dependent work out of the public request timing path.

The reset token contains an expiry and `reset_version`. On success the password hash is replaced and `reset_version` is incremented, making the token one-time. All Redis sessions for the user are revoked as part of the credential-change path.

## TOTP behavior

1. Authenticated user calls `/api/v1/auth/totp/setup`.
2. A new TOTP secret is generated and only its Fernet ciphertext is persisted.
3. The user adds the returned secret/provisioning URI to an authenticator.
4. `/api/v1/auth/totp/confirm` verifies a code and only then flips `totp_enabled=true`.
5. Future logins require `totp_code` in addition to a correct password.
6. `/api/v1/auth/totp/disable` requires a valid current TOTP code before clearing the encrypted secret.

## Bulk-upload behavior

`POST /api/v1/documents/bulk` accepts multiple `files` parts. Each file is independently validated, persisted, committed and handed to the worker queue. Results are returned per item as `queued`, `duplicate`, `rejected`, or `failed`.

A malformed/oversized/duplicate file or queue-handoff failure does not roll back successfully queued siblings. Queue-handoff failure marks the affected document/job `FAILED` so it cannot be mistaken for a successfully queued document.

## Test IDs now implementation-ready

- UM-TC-001 — registration + one-time email verification; runtime timing/mail evidence pending
- UM-TC-002 — generic login failure + real server-side session gate; deeper runtime evidence pending
- UM-TC-003 — password reset implemented; expiry/one-time/old-vs-new-password runtime evidence pending
- UM-TC-004 — logout + idle-session semantics implemented; Redis runtime evidence pending
- UM-TC-005 — optional TOTP implemented; authenticator runtime evidence pending
- DI-TC-001 — supported upload path implemented
- DI-TC-002 — exact duplicate behavior implemented
- DI-TC-003 — configurable upload-size rejection implemented
- DI-TC-004 — multi-page PDF splitting/Page persistence implemented
- DI-TC-005 — independent bulk processing/partial-failure isolation implemented

None of those tests are marked Passed merely because the code exists.

## Static/contract validation

```bash
cd backend
python -m compileall -q app alembic tests
PYTHONPATH=. pytest -q \
  tests/test_auth_timing_contracts.py \
  tests/test_model_contracts.py \
  tests/test_sprint1_contracts.py \
  tests/test_sprint1_slice3_contracts.py
```

Current result in this environment: **18 passed**.

These are source/model guardrails, not substitutes for running-stack acceptance execution. Runtime timing, SMTP behavior, Redis expiry/revocation, TOTP verification, MinIO immutability and mixed-success bulk execution still need real dependency-backed evidence before catalogue cases can become Passed.

## Runtime UM/DI acceptance harness

The repository now contains a source-review candidate runtime harness under `acceptance/` for the frozen `UM-TC-001..005` and `DI-TC-001..005` catalogue cases.

It has deliberately **not been run before independent source review**. Once reviewed, the complete local run is:

```bash
./acceptance/run-local.sh
```

The command starts a clean Docker stack including Mailpit, applies migrations, waits for health, runs functional pytest acceptance, runs anti-enumeration timing as a separate evidence stream, and writes sanitized evidence under `acceptance/evidence/<run-id>/`.

Important boundaries and known gaps are documented in `acceptance/README.md` and `acceptance/coverage-map.json`.
