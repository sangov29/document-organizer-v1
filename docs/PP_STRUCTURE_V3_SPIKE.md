# PP-StructureV3 Side-by-Side Spike — Adoption Gate

Status: criteria frozen before implementation

## Purpose

Evaluate whether structure-aware parsing materially improves downstream
classification and field assignment. PP-StructureV3 remains an optional
provider during the spike; it does not replace the current PP-OCRv5 path or
the application's trust-state, provenance, sensitivity and review contracts.

## Corpus entry gates

The adoption decision must not use the five-case synthetic OCR seed alone.

- **Pilot corpus:** at least 30 permission-cleared, redacted, manually labelled
  documents, including at least 8 `unknown` documents and at least 2 each of
  certificates, resumes/CVs, plane tickets and boarding passes. It may produce
  directional evidence and refine instrumentation, but cannot authorize
  adoption.
- **Adoption corpus:** at least 100 documents, with at least 10 examples for
  every evaluated known family and at least 20 `unknown` examples. The unknown
  set must cover certificates, resumes/CVs, plane tickets and boarding passes.

Ground truth must include document family, expected fields, values, page and
region. A second reviewer must resolve label disagreements before evaluation.
Results must include deterministic stratified-bootstrap 95% confidence
intervals; a point estimate alone is insufficient.

## Mandatory adoption criteria

PP-StructureV3 may become the default structure stage only if all criteria pass:

1. Field exact-match accuracy improves by at least 10 absolute percentage
   points on the layout-sensitive evaluation subset, the 95% confidence
   interval for the improvement excludes zero, and improvement is independently
   positive in at least three document families.
2. No evaluated document family loses more than 5 absolute percentage points
   of field exact-match accuracy.
3. Aggregate OCR character error rate does not regress by more than 2 absolute
   percentage points from the PP-OCR baseline.
4. Known-family classification macro F1 does not regress by more than 2
   absolute percentage points. Every evaluated family must retain F1 >= 0.70.
5. `unknown` precision and recall are reported independently and neither may
   regress by more than 2 absolute percentage points. The false-known rate for
   out-of-family documents must not increase.
6. General field-region localization at IoU >= 0.50 does not regress. Sensitive
   region recall must be 1.00 on the evaluation corpus and sensitive-region
   precision must be at least 0.80; no labelled sensitive pixels may remain
   outside the concealed preview region.
7. CPU p95 processing latency is no more than 2.5 times the baseline and no
   more than 15 seconds per page on the acceptance runner.
8. Peak worker memory remains within 2 GiB.
9. Processing remains local with no document-data egress. Existing owner
   isolation, sensitive-region concealment, additive corrections and provenance
   reconstruction continue to pass.
10. The provider is feature-flagged and the current path remains an explicit,
   tested rollback option.

## Evidence

The comparison must publish the corpus manifest hash, per-document outcomes,
per-family confusion matrices, `unknown` precision/recall, field and sensitive
region IoU outcomes, bootstrap intervals, aggregate accuracy, latency and
memory, plus separate JUnit and JSON evidence. Partial improvement is reported
as evidence but does not justify adoption.

Corpus documents and ground-truth values stay outside Git. Only the manifest
schema, redacted example and validator belong in this repository. Corpus
collection is the legal/process critical path; adapter implementation must not
begin until the 30-document pilot entry gate passes.

PP-OCR model-version experiments, including any PP-OCRv6 candidate, must use
the same corpus and gates and remain separate from the structure-stage change.
