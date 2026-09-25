# Build Status — Verified V1 Runtime Baseline

Baseline date: 25 September 2026  
Verified commit: `1bb1493f51381f17e889f3f4823c091f8f393aab`  
Evidence: GitHub Runtime Acceptance #33  
GitHub Actions run ID: `36086256438`  
Evidence URL: https://github.com/sangov29/document-organizer-v1/actions/runs/36086256438  
Evidence artifact digest: `sha256:5da4abbcd8e439b4e25e5df329989108f31727d521efd441c837b106ec3ccbcb`

## Current result

- Functional runtime acceptance: **64 passed, 0 failed, 0 errors, 0 skipped**
- Frozen catalogue coverage: **50 exact IDs** across UM, DI, PP, CR, CL, EX, PR, VA, SR, OR, IN and SEC
- Anti-enumeration timing: **3 passed**
- Browser journey: **1 passed**
- Labelled deterministic OCR regression evaluation: **5 passed**, aggregate CER/WER **0.0000/0.0000**
- Backend source/model/behavioral contracts: **104 passed**, with separate mandatory JUnit evidence
- Bounded concurrent write/OCR qualification: **4/4 completed** at concurrency 2, submit p95 **0.052s**, completion p95 **19.783s**
- Acceptance SLO gate: readiness healthy, minimum traffic met, API 5xx ratio within 1%, successful-request p95 within 2.5 seconds
- Controlled authenticated read-load gate: **240 requests at concurrency 8**, with latency, throughput, error and unexpected-429 limits enforced
- `source_contract_exit=0`, `functional_exit=0`, `timing_exit=0`, `ocr_evaluation_exit=0`, `ui_exit=0`, `load_exit=0`, `slo_exit=0`, `backup_restore_exit=0`
- Known catalogue gaps reported by the harness: **none**
- Frontend acceptance runtime: Playwright **1.63.0**, with the previously reported dependency advisories removed

Runtime Acceptance #33 confirms dependency-aware process liveness and traffic readiness for PostgreSQL, Redis and object storage. It also proves isolated PostgreSQL dump/restore equivalence, MinIO object round-trip restore, the measurable acceptance SLO gate, controlled authenticated list/search load, bounded concurrent write/OCR completion, TOTP threshold isolation/recovery and API/browser security headers. The larger timing sample preserves the existing anti-enumeration tolerances while reducing false failures at a discrete KS boundary.

Run #33 verifies corpus manifest schema v0.2 and closes the declared-review loophole: a `two-reviewer-resolved` claim is rejected unless two distinct, non-placeholder reviewers provide independent complete labels, validator-derived agreement/disagreement axes are consistent, and disagreements have resolved joint or independent third-party adjudication evidence.

Run #31 additionally closes the release-critical resilience gaps with executable evidence: committed OCR artifacts are reused on task redelivery without double-processing, migration `0013` repairs a seeded duplicate version history before creating the unique index, and a simulated database version collision exercises the upload handler's stable `409 version_conflict`, rollback and orphan-object cleanup path.

Runs #13–#16 introduced the isolated backup/restore gate and corrected immutable database comparison and a document-version upload race. Runs #17–#19 then exposed the object-probe container import defect; Runs #20 and #21 verify the corrected probe and its source contract.

Run #9 established privacy-safe public share throttling and race-safe document version numbering, then exposed the share-readiness defect. Runs #6–#8 exercised and corrected composite share-token handling. Runtime Acceptance #5 confirmed document version history; #4 confirmed content-sniffing; #3 confirmed declared MIME/magic-byte upload verification and safe mixed-bulk rejection. Runtime Acceptance #1 under the renamed workflow (project sequence Run #65) confirmed occurrence-level sensitive OCR search filtering. Project Run #64 confirmed per-owner reminder preferences; Run #63 confirmed owner-scoped expiry/due-date reminders; Run #62 confirmed owner-scoped tags and collections plus the private corpus-intake CLI after Run #61 exposed and corrected an Alembic import-order defect. Run #57 confirmed Redis-backed login/TOTP attempt throttling. Run #56 confirmed the Next.js 16.3.5 upgrade, lockfile-reproducible frontend build, Docker development-origin configuration, hydration guard and single-flight email verification under React Strict Mode. Run #52 confirmed the immutable MinIO Community image correction.

Earlier project-sequence Run #31 closed the two extraction/provenance defects found by project-sequence Run #30:

- `EX-TC-004`: inferred `issuing_authority` retains the complete value and remains `trust_state=inferred`.
- `PR-TC-002`: every returned sensitive textual-field `visual_region_id` resolves to exactly one serialized `sensitive_regions` entry.

## Implemented product scope

### User management and security

- Anti-enumerating registration, login and password-reset behavior
- One-time expiring verification and password-reset tokens
- Redis-backed idle sessions, logout and credential-change revocation
- Redis-backed login/TOTP throttling with privacy-safe subject keys
- Optional TOTP with encrypted-at-rest secret and explicit confirmation
- Owner-scoped document, OCR, analysis, review, export and reveal operations
- Default masking of sensitive financial values and signature regions
- Audited, non-cached owner reveal with non-enumerating foreign-resource denial

### Document processing

- PDF/JPG/PNG single and bulk upload with size, declared-type and magic-byte content validation
- Immutable source/page storage and SHA-256 duplicate detection
- Explicit duplicate keep with canonical linkage and audit evidence
- Immutable document replacement/version history with direct and logical-group lineage
- Database-enforced logical version-number uniqueness with deterministic migration repair and stable conflict handling
- Revocable, time-limited read-only sharing with hashed bearer tokens, masked structured fields and privacy-safe per-link throttling
- Share creation gated on completed structured analysis
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
- Sequential Alembic chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013`
- Migration `0013` enforces logical document-version uniqueness across root and successor rows

## Acceptance evidence boundary

Runtime Acceptance #33 proves the deterministic V1 behavior at commit `1bb1493` against the Docker acceptance stack: PostgreSQL, Redis, MinIO, Mailpit, API, Celery worker, frontend and Playwright. It also proves isolated database and object-storage restoration, the synthetic acceptance SLO gate, bounded authenticated read load, bounded concurrent document writes through OCR completion, retry-safe OCR reuse, seeded migration repair, behavioral version-conflict handling, corpus reviewer-evidence enforcement, explicit TOTP throttling behavior and security response headers within the acceptance environment. The workflow counter restarted because `.github/workflows/blank.yml` was renamed to `runtime-acceptance.yml`. Mail evidence is limited to application queueing, token lifecycle, SMTP handoff and local Mailpit receipt; it is not an external-provider delivery claim.

The green deterministic suite is not a corpus-wide OCR/classification/extraction accuracy benchmark. The five OCR documents are synthetic regression fixtures that validate the evaluation harness; their perfect CER/WER must not be presented as real-world model accuracy. Model precision, recall, F1, false-known/false-unknown rates, throughput, load, resilience, retention periods and production infrastructure qualification remain separate gates.

Full-text OCR search confirms raw database candidates against the same redacted text returned by the public OCR endpoint, so sensitive-only occurrences remain excluded while independent ordinary-text occurrences are searchable. For a text query, V1 performs this privacy confirmation in Python before pagination; this is appropriate for a personal library but must move to indexed redacted search material before large-scale deployment.

## Next product decision

The PP-StructureV3 adoption criteria and private-corpus manifest contract remain frozen, but the experiment is **parked, not cancelled**. Its target date is unset pending an owner-supplied corpus. The model adapter remains gated until the private pilot contains at least 30 permission-cleared documents with independent labels from two distinct reviewers, resolved adjudication evidence, and passes `evaluation/validate_corpus_manifest.py --mode pilot --verify-files`.

With runtime qualification and the release-critical resilience tests verified, general platform feature development is frozen. Corpus manifest schema v0.2 now derives reviewer agreement and disagreement axes from independent evidence and rejects placeholder, same-reviewer or unresolved-adjudication claims. The next required input is the permission-cleared, independently labelled corpus; PP-StructureV3 remains out of scope until that gate is satisfied.
