# Private evaluation corpus workflow

Real documents, consent records and ground-truth labels must remain local. Git
contains only the tooling, schema example and tests.

## 1. Add permission-cleared documents

On Windows PowerShell, from the repository root:

```powershell
New-Item -ItemType Directory -Force evaluation/private
```

Copy only permission-cleared PDF, JPG, JPEG or PNG documents into
`evaluation/private`. Remove unnecessary personal information first. Duplicate
file content is rejected because duplicates would distort accuracy results.

## 2. Create the draft manifest

```powershell
python evaluation/bootstrap_corpus.py
```

This creates ignored file `evaluation/corpus-manifest.json`, calculates SHA-256
hashes and creates stable IDs. For each document, replace `TODO` values and add
the expected fields, page numbers, bounding boxes and sensitivity decisions.

To add or rename corpus files without losing completed labels:

```powershell
python evaluation/bootstrap_corpus.py --update
```

Updates match records by content hash. A record whose source file is missing is
retained so accidental deletion cannot silently change the evaluation set.

## 3. Review and validate

After two reviewers resolve all label disagreements, set `label_review` to
`two-reviewer-resolved` and run:

```powershell
python evaluation/validate_corpus_manifest.py evaluation/corpus-manifest.json --mode pilot --verify-files
```

The pilot requires 30 documents, including two each of certificates,
resumes/CVs, plane tickets and boarding passes. It provides directional
evidence only. The 100-document adoption gate and full decision criteria are in
`docs/PP_STRUCTURE_V3_SPIKE.md`.

Never run `git add -f` against the private corpus paths. The repository ignores
the documents, working manifest and label directory by design.
