# Private evaluation corpus workflow

Real documents, consent records and ground-truth labels must remain local. Git
contains only the tooling, schema example and tests.

## 1. Intake one permission-cleared document

Use the restricted local CLI. It accepts exactly one file, records the written
permission basis, source provenance and two assigned reviewers, rejects
duplicate content by SHA-256, and updates the ignored working manifest:

```bash
python evaluation/intake_document.py /safe/path/document.jpg \
  --permission-basis owner_document \
  --provenance "Owner-supplied mobile photograph" \
  --reviewer-a reviewer-a-handle \
  --reviewer-b reviewer-b-handle
```

Supported permission bases are `owner_document`, `written_consent`,
`realistic_synthetic`, and `public_domain`. Do not put personal names or document
contents in the provenance string.

## 2. Add permission-cleared documents manually

On Windows PowerShell, from the repository root:

```powershell
New-Item -ItemType Directory -Force evaluation/private
```

Copy only permission-cleared PDF, JPG, JPEG or PNG documents into
`evaluation/private`. Remove unnecessary personal information first. Duplicate
file content is rejected because duplicates would distort accuracy results.

## 3. Create the draft manifest

```powershell
python evaluation/bootstrap_corpus.py
```

This creates ignored file `evaluation/corpus-manifest.json`, calculates SHA-256
hashes and creates stable IDs. For each document, replace `TODO` values and add
the expected fields, page numbers, bounding boxes and sensitivity decisions.
Name two distinct reviewers before labelling begins. Each reviewer must record
their own complete `reviewer_a_label` or `reviewer_b_label` without copying the
other reviewer's answers.

To add or rename corpus files without losing completed labels:

```powershell
python evaluation/bootstrap_corpus.py --update
```

Updates match records by content hash. A record whose source file is missing is
retained so accidental deletion cannot silently change the evaluation set.

## 4. Review and validate

The validator derives `reviewer_agreement` and `disagreement_axes` across family,
unknown status, field presence, value, page and region; it does not trust a
declared agreement. Disagreements require either joint adjudication (listing both
reviewers) or an independent third-party adjudicator, a resolved label and a
non-placeholder rationale. Unresolved records are rejected. After every record
is resolved, set `label_review` to `two-reviewer-resolved` and run:

```powershell
python evaluation/validate_corpus_manifest.py evaluation/corpus-manifest.json --mode pilot --verify-files
```

The pilot requires 30 documents, including two each of certificates,
resumes/CVs, plane tickets and boarding passes. It provides directional
evidence only. The 100-document adoption gate and full decision criteria are in
`docs/PP_STRUCTURE_V3_SPIKE.md`.

Never run `git add -f` against the private corpus paths. The repository ignores
the documents, working manifest and label directory by design.
