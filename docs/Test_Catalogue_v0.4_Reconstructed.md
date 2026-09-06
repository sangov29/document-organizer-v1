# V1 Test Catalogue v0.4 — Reconstructed Baseline

Status: controlled reconstruction, 6 September 2026.

Authority: `RTM_v0.2_Traceability_Baseline_Candidate.md`, the implemented public API contract, and retained runtime evidence through Run #28. This file replaces no unavailable historical document. Claims are limited to deterministic V1 acceptance fixtures; corpus-wide AI accuracy requires separate labelled evaluation.

## Content recognition

### CR-TC-002 — Signature-region detection

1. Upload a synthetic banking document containing a labelled signature line.
2. Complete preprocessing and OCR through the normal worker pipeline.
3. Verify a signature visual region is stored with page ID, bounding box, provider, model version and confidence.
4. Verify ordinary analysis returns only concealed region metadata.
5. Verify the owner can explicitly reveal the region and another account cannot.

## Structured extraction

### EX-TC-001 — Predefined family fields

Upload Identity, Utility and Banking fixtures; verify the active versioned schema is selected and every defined field is attempted.

### EX-TC-002 — Field confidence

Verify every extracted value has an independent confidence in `[0,1]`; `not_found` fields have no fabricated confidence.

### EX-TC-003 — Explicit not-found state

Omit one expected field and verify it remains present with `value=null`, `confidence=null`, and `trust_state=not_found`.

### EX-TC-004 — Separate inferred information

Verify inferred values use `trust_state=inferred`, remain distinguishable from OCR-extracted values, and require review.

### EX-TC-005 — Confirm inferred field

Confirm an inferred field through the owner-scoped public API and verify the active state becomes `confirmed` with an audit event.

### EX-TC-006 — Bounded schema extraction

Include plausible but undefined labels and verify no unversioned/unbounded fields are created for a known family.

### EX-TC-007 — Preserve Unknown OCR

Upload an out-of-distribution document, retain the `unknown` classification, and verify page-linked OCR text remains retrievable through the owner-scoped API.

## Provenance

### PR-TC-001 — Source page

Verify each extracted field identifies its source document and page.

### PR-TC-002 — Bounding region

Verify a locatable extracted value identifies a visual region with page-relative coordinates.

### PR-TC-003 — Full field provenance

Verify source document/page/region, provider, model or schema version, method, confidence and processing timestamp are returned together.

### PR-TC-005 — Classification provenance

Verify the active classification has document/page source, provider, model version, method, confidence and timestamp.

### PR-TC-006 — Provenance reconstruction

Reconstruct classification and field lineage from public analysis responses; after correction, verify original model provenance and correction linkage remain intact.

## Acceptance rules

- Tests drive behavior through public HTTP APIs.
- Database or object-storage inspection is permitted only for persistence or integrity evidence explicitly unavailable publicly.
- Ownership isolation uses the same non-enumerating response for foreign and nonexistent identifiers.
- Synthetic fixtures must be unique per run.
- No test may weaken a security, confidence or review threshold merely to pass.
