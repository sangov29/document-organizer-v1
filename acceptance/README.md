# V1 Runtime Acceptance Harness

This harness executes 50 frozen catalogue IDs across UM, DI, PP, CR, CL, EX,
PR, VA, SR, OR, IN and SEC against the running V1 stack. Run #31 is the
verified baseline: 53 functional tests, 3 timing probes and 1 browser journey
all passed with zero exit codes and no known catalogue gaps.

## Boundary rules

- Product behavior is driven through the public HTTP API. Direct inspection is limited to persistence or integrity evidence that is not exposed publicly and is explicitly required by the catalogue.
- Direct PostgreSQL/config inspection is used only for evidence the frozen catalogue explicitly asks for: verification state/password-storage inspection, page count/order/source linkage, and configured upload limit. Processing-job/correlation inspection is additionally used only in failure diagnostics.
- Redis is **not** mutated or used to make auth assertions; logout/reset/idle behavior is proved by replaying issued JWTs through the API.
- Verification/reset tokens are retrieved from Mailpit's local mail-sink interface. There is no test-only backend token endpoint.
- Mail evidence proves application queueing, token lifecycle, SMTP handoff to the local sink, and sink receipt only. It does not claim any external email-delivery-provider behavior.
- JWTs, passwords, verification/reset links, TOTP secrets, and provisioning URIs are redacted from diagnostics.

## Catalogue mapping

See `coverage-map.json` for the exact 50-ID mapping and step-level evidence
boundaries. Ownership-safe retrieval, duplicate keep, preprocessing, OCR,
classification, extraction, provenance, review, organization, search, export
and sensitive-data controls all have executable runtime coverage.

PP evidence includes page-linked quality metadata and before/after normalized
images in the run's `preprocessing/` directory. Optional noise reduction ships
disabled until the OCR stage can provide the required paired recognition comparison.

The Playwright journey supplies separate browser evidence for registration,
verification, login, upload, duplicate keep, inert filename rendering,
document analysis/review and logout. Functional API, timing and UI results
remain separate evidence streams.

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

## Browser evidence

The same command also runs a Playwright browser journey against the real
frontend. It covers registration, Mailpit-backed verification, login, upload,
duplicate detection and explicit keep, document details, inert rendering of an
unusual filename, and logout. It publishes separate UI JUnit, screenshots and
failure traces under the run evidence directory.

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
8. runs the browser-level frontend journey and captures UI JUnit/screenshots;
9. captures sanitized pytest output, Docker stats, test failure diagnostics and container logs.

Evidence is written under `acceptance/evidence/<run-id>/`.
