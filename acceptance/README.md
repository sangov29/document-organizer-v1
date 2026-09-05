# UM/DI Runtime Acceptance Harness

This harness executes the already-baselined `UM-TC-001..005` and `DI-TC-001..005` behaviors against the running V1 stack. It does not invent a second acceptance-test namespace.

## Boundary rules

- Test actions are driven through the public HTTP API.
- Direct PostgreSQL/config inspection is used only for evidence the frozen catalogue explicitly asks for: verification state/password-storage inspection, page count/order/source linkage, and configured upload limit. Processing-job/correlation inspection is additionally used only in failure diagnostics.
- Redis is **not** mutated or used to make auth assertions; logout/reset/idle behavior is proved by replaying issued JWTs through the API.
- Verification/reset tokens are retrieved from Mailpit's local mail-sink interface. There is no test-only backend token endpoint.
- Mail evidence proves application queueing, token lifecycle, SMTP handoff to the local sink, and sink receipt only. It does not claim any external email-delivery-provider behavior.
- JWTs, passwords, verification/reset links, TOTP secrets, and provisioning URIs are redacted from diagnostics.

## Catalogue mapping

See `coverage-map.json`. Two known implementation gaps are deliberately visible rather than silently waived:

1. `UM-TC-002` steps 5-6 cannot fully execute because there is no public document/resource-by-ID endpoint to tamper with yet.
2. `DI-TC-002` step 5 cannot execute because no public duplicate `proceed/keep` override exists yet.

Those subtests are strict `xfail`/known-gap evidence. The containing catalogue test must not be called fully Passed while they remain.

UI-only screenshot requirements in `UM-TC-001` step 1 and `DI-TC-001` steps 6-7 are represented only by their API equivalents in this API-only harness and remain separate UI evidence if literal catalogue completion is required.

## Timing evidence

Timing is deliberately separate from normal functional JUnit. `tools/timing_probe.py` collects raw samples for:

- registration: new vs already-registered email;
- login: real account + wrong password vs nonexistent account;
- password reset request: real vs nonexistent account.

The probe uses 50 samples and 6 warmups per group by default. Within every
pair it uses a recorded, seeded, balanced randomized branch-first order. This
reduces systematic container drift while keeping the published median, p95 and
KS acceptance thresholds unchanged. Sample and warmup counts must be even.

Published outputs include raw samples, median, p95, relative deltas and a two-sample Kolmogorov-Smirnov statistic.

The local harness tolerance is **not a product NFR benchmark**. It is a regression guard and is configurable:

- median relative delta <= `TIMING_MEDIAN_REL_TOL` (default `0.25` = 25%);
- p95 relative delta <= `TIMING_P95_REL_TOL` (default `0.35` = 35%);
- KS statistic <= `TIMING_KS_MAX` (default `0.35`).

Functional JUnit and timing JUnit are separate files. The orchestration command reports both statuses independently.

## One-command execution

From the restored `document-organizer-v1/` directory:

```bash
./acceptance/run-local.sh
```

The script:

1. creates fresh synthetic acceptance secrets and a unique run ID;
2. resets local Docker volumes;
3. brings up PostgreSQL, Redis, MinIO, Mailpit, API, worker and frontend;
4. applies Alembic migrations;
5. waits for API and Mailpit health;
6. runs functional pytest acceptance and writes JUnit XML;
7. runs the separate timing probe and writes timing JSON + timing JUnit XML;
8. captures sanitized pytest output, Docker stats, test failure diagnostics and container logs.

Evidence is written under `acceptance/evidence/<run-id>/`.
