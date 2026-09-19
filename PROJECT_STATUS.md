# Build Status — Verified V1 Runtime Baseline

Baseline date: 19 September 2026  
Verified commit: `9948056cd6bb7def1abe8c6b3c86440e3646ff9e`  
Evidence: GitHub Runtime Acceptance Run #57

## Current result

- Functional runtime acceptance: **54 passed, 0 failed, 0 errors, 0 skipped**
- Frozen catalogue coverage: **50 exact IDs** across UM, DI, PP, CR, CL, EX, PR, VA, SR, OR, IN and SEC
- Anti-enumeration timing: **3 passed**
- Browser journey: **1 passed**
- Labelled deterministic OCR evaluation: **5 passed**, aggregate CER/WER **0.0000/0.0000**
- `functional_exit=0`, `timing_exit=0`, `ocr_evaluation_exit=0`, `ui_exit=0`
- Known catalogue gaps reported by the harness: **none**

Run #57 additionally confirms Redis-backed login/TOTP attempt throttling. Run #56 confirmed the Next.js 16.3.5 upgrade, lockfile-reproducible frontend
build, Docker development-origin configuration, hydration guard and single-flight
email verification under React Strict Mode. Run #52 confirmed the immutable MinIO Community image correction after
Run #51 was blocked before startup by a nonexistent container tag.

Run #31 closed the two defects found by Run #30:

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
- PP-OCRv5 printed-text OCR with page, word and bounding-box lineage; Tesseract remains an explicit fallback provider
- Seven known classification families plus explicit `unknown`
- Versioned predefined extraction for Identity, Utility, Banking and Invoice/Receipt, plus generic Unknown extraction with confidence, criticality and explicit `not_found`
- Classification/field review, correction, confirmation and history preservation
- Organization, owner-scoped search, date sorting and pagination
- Stable JSON and normalized multi-document CSV export
- Permanent owner-controlled deletion of document database and object-storage data while retaining a value-free audit record
- Owner-wide and per-document audit history plus versioned JSON audit export
- Multi-page preview with extracted/sensitive-region overlays and server-side redacted page rendering

### Data model and migrations

- **13 persisted domain entities**, including `PreprocessingResult`
- Sequential Alembic chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008`

## Acceptance evidence boundary

Run #52 proves deterministic V1 behavior against the Docker acceptance stack: PostgreSQL, Redis, MinIO, Mailpit, API, Celery worker, frontend and Playwright. Mail evidence is limited to application queueing, token lifecycle, SMTP handoff and local Mailpit receipt; it is not an external-provider delivery claim.

The green deterministic suite is not a corpus-wide OCR/classification/extraction accuracy benchmark. Model precision, recall, F1, false-known/false-unknown rates, throughput, load, resilience, retention periods and production infrastructure qualification remain separate gates.

## Next product decision

The PP-StructureV3 adoption criteria and private-corpus manifest contract are
frozen. The model adapter remains gated until the private pilot contains at
least 30 permission-cleared and manually labelled documents and passes
`evaluation/validate_corpus_manifest.py --mode pilot --verify-files`.

While corpus collection proceeds, unblocked work focuses on production security
and operational readiness. The Next.js maintenance increment is complete; the
next security increment adds Redis-backed login and TOTP attempt throttling.
