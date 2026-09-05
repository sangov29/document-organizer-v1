# Build Status — Sprint 1 / Slice 3

## Implemented

### UM
- Registration/login anti-enumeration password-work hardening
- One-time expiring email verification using signed token + `User.verification_version`
- Verification delivery queued for both registration branches
- Redis-backed per-login session IDs with server-enforced idle TTL
- Logout revokes the active Redis session
- Password-reset request with generic response and no in-request account-existence query
- Password-reset delivery queued asynchronously for every request
- One-time expiring password-reset token using `User.reset_version`
- Successful password reset replaces the password hash, increments `reset_version`, records an auth audit event, and revokes all active server-side sessions
- Optional TOTP setup/confirm/disable flow
- TOTP secret encrypted at rest using a required Fernet key; plaintext secret is not persisted
- Login requires a valid TOTP code only after TOTP has been explicitly confirmed/enabled

### DI
- PDF/JPG/PNG upload, limit checks, exact SHA-256 duplicate detection
- Immutable source object keys and write-once storage behavior
- Worker-side PDF page splitting with `pypdf`
- Immutable per-page PDF objects and ordered `Page` persistence
- Single-page `Page` persistence for JPG/PNG
- Idempotent page splitting on retries
- Bulk upload endpoint with one try/commit/queue boundary per file
- Rejected/duplicate/failed batch items do not roll back successfully queued siblings
- Queue-handoff failure is persisted as document/job `FAILED` rather than masquerading as queued

### Data / migrations / tests
- 12 baseline entities retained; no new domain entity introduced
- User auth state extended with `reset_version` and encrypted TOTP-secret ciphertext
- Alembic chain: `0001 → 0002 → 0003`
- 18 current backend source/model contract tests passing in this environment
- backend/app/test Python compilation clean

## Still not claimed Passed

- UM-TC-001: running-stack response/timing comparison and real mail transport evidence required
- UM-TC-002: running login/session/authorization evidence required
- UM-TC-003: running reset-link expiry, one-time use, old-password failure, new-password success and session-revocation evidence required
- UM-TC-004: running Redis idle-expiry/logout replay evidence required
- UM-TC-005: running authenticator/TOTP setup, confirmation, login challenge and disable evidence required
- DI-TC-001–005: running Postgres/MinIO/Celery tests with real files and mixed-success bulk batches required

## Environment limitation during this patch

The active execution environment has `cryptography`, FastAPI, SQLAlchemy and `pypdf`, but does not currently have `pyotp`, `redis`, or `celery` installed. Outbound package installation is not assumed. Therefore this slice was validated with compilation plus source/model contracts; it does **not** claim runtime acceptance evidence.

## Next coding slice

1. Bring up / exercise the full local dependency stack and capture UM/DI running-stack acceptance evidence.
2. Close any defects found by UM-TC-001/002/003/004/005 and DI-TC-001–005 execution.
3. Then move to PP: orientation correction, low-quality assessment, deskew and optional comparative noise reduction.
4. After PP is stable, begin OCR + CL/CR/EX for Utility + Identity + Unknown.

## Runtime acceptance harness — verified baseline

The runtime UM/DI acceptance harness under `acceptance/` was executed
successfully in GitHub Actions Run #7. That evidence recorded 11 passes, two
then-known gaps, zero functional failures, and passes for all three separate
anti-enumeration timing probes.

Coverage is explicitly mapped to `UM-TC-001..005` and `DI-TC-001..005`. The harness drives behavior through the public API, uses Mailpit as a local SMTP/test-mail sink, generates unique accounts and per-run document content, produces functional JUnit plus separate timing JSON/JUnit, and collects redacted failure diagnostics.

The two Run #7 gaps now have implementations and runtime tests prepared for the
next evidence run: ownership-safe public resource-by-ID retrieval and explicit
duplicate `keep` with canonical linkage and audit evidence.

Literal browser/UI screenshot evidence is also not claimed by this API-only harness. See `acceptance/coverage-map.json` for the exact step-level crosswalk.
