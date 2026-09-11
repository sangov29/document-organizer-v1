# PP-StructureV3 Side-by-Side Spike — Adoption Gate

Status: criteria frozen before implementation

## Purpose

Evaluate whether structure-aware parsing materially improves downstream
classification and field assignment. PP-StructureV3 remains an optional
provider during the spike; it does not replace the current PP-OCRv5 path or
the application's trust-state, provenance, sensitivity and review contracts.

## Corpus entry gate

The adoption decision must not use the five-case synthetic OCR seed alone.
The evaluation corpus must contain at least 30 permission-cleared, redacted,
manually labelled documents, including at least five out-of-family examples
across certificates, resumes/CVs, plane tickets or boarding passes. Ground
truth must include document family, expected fields, values, page and region.

## Mandatory adoption criteria

PP-StructureV3 may become the default structure stage only if all criteria pass:

1. Field exact-match accuracy improves by at least 10 absolute percentage
   points on the layout-sensitive evaluation subset.
2. No evaluated document family loses more than 5 absolute percentage points
   of field exact-match accuracy.
3. Aggregate OCR character error rate does not regress by more than 2 absolute
   percentage points from the PP-OCR baseline.
4. Known-family classification macro F1 does not regress by more than 2
   absolute percentage points; false-known outcomes for out-of-family documents
   do not increase.
5. CPU p95 processing latency is no more than 2.5 times the baseline and no
   more than 15 seconds per page on the acceptance runner.
6. Peak worker memory remains within 2 GiB.
7. Processing remains local with no document-data egress. Existing owner
   isolation, sensitive-region concealment, additive corrections and provenance
   reconstruction continue to pass.
8. The provider is feature-flagged and the current path remains an explicit,
   tested rollback option.

## Evidence

The comparison must publish the corpus manifest hash, per-document outcomes,
aggregate accuracy, latency and memory, plus separate JUnit and JSON evidence.
Partial improvement is reported as evidence but does not justify adoption.

PP-OCR model-version experiments, including any PP-OCRv6 candidate, must use
the same corpus and gates and remain separate from the structure-stage change.
