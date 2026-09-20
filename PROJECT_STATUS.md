# Build Status — Verified V1 Runtime Baseline

Baseline date: 20 September 2026  
Verified commit: `ecc3b71dbbe5d3563120e96b511f8a36653958e3`  
Evidence: GitHub Runtime Acceptance #5 under the renamed workflow

## Current result

- Functional runtime acceptance: **58 passed, 0 failed, 0 errors, 0 skipped**
- Frozen catalogue coverage: **50 exact IDs** across UM, DI, PP, CR, CL, EX, PR, VA, SR, OR, IN and SEC
- Anti-enumeration timing: **3 passed**
- Browser journey: **1 passed**
- Labelled deterministic OCR evaluation: **5 passed**, aggregate CER/WER **0.0000/0.0000**
- `functional_exit=0`, `timing_exit=0`, `ocr_evaluation_exit=0`, `ui_exit=0`
- Known catalogue gaps reported by the harness: **none**
- Backend source/model contracts: **69 passed**, with separate mandatory JUnit evidence
- Frontend acceptance runtime: Playwright **1.63.0**, with the previously reported dependency advisories removed

Runtime Acceptance #3 confirms declared MIME/magic-byte upload verification and safe mixed-bulk rejection. Runtime Acceptance #1 under the renamed workflow (project sequence Run #65) confirms occurrence-level sensitive OCR search filtering. Project Run #64 confirms per-owner reminder preferences and migration `0010`; Run #63 confirms owner-scoped expiry/due-date reminders, status boundaries and dashboard presentation. Run #62 confirms owner-scoped tags and collections, the private corpus-intake CLI contract and the sequential `0009` migration after Run #61 exposed and corrected an Alembic import-order defect. Run #57 additionally confirms Redis-backed login/TOTP attempt throttling. Run #56 confirmed the Next.js 16.3.5 upgrade, lockfile-reproducible frontend
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

- PDF/JPG/PNG single and bulk upload with size, declared-type and magic-byte content validation
- Immutable source/page storage and SHA-256 duplicate detection
- Explicit duplicate keep with canonical linkage and audit evidence
- Immutable document replacement/version history with direct and logical-group lineage
- Revocable, time-limited read-only sharing with hashed bearer tokens and masked structured fields (pending Runtime Acceptance #6 evidence)
- Independent bulk-item failure boundaries
- Multi-page PDF splitting and page persistence
- Orientation correction, quality/blur/resolution assessment and deskew routing
- PP-OCRv5 printed-text OCR with page, word and bounding-box lineage; Tesseract remains an explicit fallback provider
- Seven known classification families plus explicit `unknown`
- Versioned predefined extraction for Identity, Utility, Banking and Invoice/Receipt, plus generic Unknown extraction with confidence, criticality and explicit `not_found`
- Classification/field review, correction, confirmation and history preservation
- Organization, owner-scoped search, date sorting and pagination
- Owner-scoped full-text OCR search, with sensitivity-tagged extracted values excluded from OCR matching
- User-defined, owner-scoped tags and collections with document filtering
- Owner-scoped in-app expiry and due-date reminders with per-owner enable/window preferences
- Stable JSON and normalized multi-document CSV export
- Permanent owner-controlled deletion of document database and object-storage data while retaining a value-free audit record
- Owner-wide and per-document audit history plus versioned JSON audit export
- Multi-page preview with extracted/sensitive-region overlays and server-side redacted page rendering

### Data model and migrations

- **16 persisted domain entities**, including `PreprocessingResult`, `Tag`, `Collection` and `ShareLink`
- Sequential Alembic chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011`; `0012` share-link persistence is pending Runtime Acceptance #6 evidence

## Acceptance evidence boundary

Runtime Acceptance #5 proves the existing deterministic V1 behavior at commit `ecc3b71` against the Docker acceptance stack: PostgreSQL, Redis, MinIO, Mailpit, API, Celery worker, frontend and Playwright. The workflow counter restarted because `.github/workflows/blank.yml` was renamed to `runtime-acceptance.yml`. Mail evidence is limited to application queueing, token lifecycle, SMTP handoff and local Mailpit receipt; it is not an external-provider delivery claim. The 58-test functional result includes content-signature validation, occurrence-level privacy-safe search, owner-scoped reminders, tags, collections, immutable version history and current-version query semantics; the 69-test source-contract result includes upload signatures, reminder preferences, document versioning, current-version query semantics and the corpus-intake CLI contract.

The green deterministic suite is not a corpus-wide OCR/classification/extraction accuracy benchmark. Model precision, recall, F1, false-known/false-unknown rates, throughput, load, resilience, retention periods and production infrastructure qualification remain separate gates.

Full-text OCR search confirms raw database candidates against the same redacted
text returned by the public OCR endpoint, so sensitive-only occurrences remain
excluded while independent ordinary-text occurrences are searchable. For a
text query, V1 performs this privacy confirmation in Python before pagination;
this is appropriate for a personal library but must move to indexed redacted
search material before large-scale deployment.

## Next product decision

The PP-StructureV3 adoption criteria and private-corpus manifest contract remain
frozen, but the experiment is **parked, not cancelled**. Its target date is
unset pending an owner-supplied corpus. The model adapter remains gated until
the private pilot contains at least 30 permission-cleared, two-reviewer-labelled
documents and passes `evaluation/validate_corpus_manifest.py --mode pilot --verify-files`.

While corpus collection proceeds, unblocked work focuses on product usability,
production security and operational readiness. The Next.js and Playwright
maintenance increments and Redis-backed login/TOTP throttling are complete.
