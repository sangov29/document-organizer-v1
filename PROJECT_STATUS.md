# Build Status — Verified V1 Runtime Baseline

Baseline date: 6 September 2026  
Verified commit: `d0773b7725817d36d5786d645c95ebef03b86352`  
Evidence: GitHub Runtime Acceptance Run #31

## Current result

- Functional runtime acceptance: **53 passed, 0 failed, 0 errors, 0 skipped**
- Frozen catalogue coverage: **50 exact IDs** across UM, DI, PP, CR, CL, EX, PR, VA, SR, OR, IN and SEC
- Anti-enumeration timing: **3 passed**
- Browser journey: **1 passed**
- `functional_exit=0`, `timing_exit=0`, `ui_exit=0`
- Known catalogue gaps reported by the harness: **none**

Run #31 also closes the two defects found by Run #30:

- `EX-TC-004`: inferred `issuing_authority` retains the complete value and remains `trust_state=inferred`.
- `PR-TC-002`: every returned sensitive textual-field `visual_region_id` resolves to exactly one serialized `sensitive_regions` entry.

## Implemented product scope

### User management and security

- Anti-enumerating registration, login and password-reset behavior
- One-time expiring verification and password-reset tokens
- Redis-backed idle sessions, logout and credential-change revocation
- Optional TOTP with encrypted-at-rest secret and explicit confirmation
- Owner-scoped document, OCR, analysis, review, export and reveal operations
- Default masking of sensitive financial values and signature regions
- Audited, non-cached owner reveal with non-enumerating foreign-resource denial

### Document processing

- PDF/JPG/PNG single and bulk upload with size/type validation
- Immutable source/page storage and SHA-256 duplicate detection
- Explicit duplicate keep with canonical linkage and audit evidence
- Independent bulk-item failure boundaries
- Multi-page PDF splitting and page persistence
- Orientation correction, quality/blur/resolution assessment and deskew routing
- Printed-text OCR with page, word and bounding-box lineage
- Seven known classification families plus explicit `unknown`
- Versioned predefined and generic extraction with confidence, criticality and explicit `not_found`
- Classification/field review, correction, confirmation and history preservation
- Organization, owner-scoped search, date sorting and pagination
- Stable JSON and normalized multi-document CSV export

### Data model and migrations

- **13 persisted domain entities**, including `PreprocessingResult`
- Sequential Alembic chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008`

## Acceptance evidence boundary

Run #31 proves deterministic V1 behavior against the Docker acceptance stack: PostgreSQL, Redis, MinIO, Mailpit, API, Celery worker, frontend and Playwright. Mail evidence is limited to application queueing, token lifecycle, SMTP handoff and local Mailpit receipt; it is not an external-provider delivery claim.

The green deterministic suite is not a corpus-wide OCR/classification/extraction accuracy benchmark. Model precision, recall, F1, false-known/false-unknown rates, throughput, load, resilience, retention periods and production infrastructure qualification remain separate gates.

## Next product decision

The implementation has reached a clean 50-ID runtime baseline. Before adding another feature, define and freeze the next catalogue increment. Recommended order:

1. labelled-corpus AI evaluation for OCR, classification and extraction;
2. production lifecycle controls: retention, deletion and recovery;
3. operational readiness: observability, load/resilience and deployment qualification;
4. expanded review/search/export browser journeys.

No Run #32 feature scope is claimed until one of these increments has explicit acceptance criteria.
