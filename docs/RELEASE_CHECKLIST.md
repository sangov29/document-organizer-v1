# Release checklist

A release is blocked unless every item below is complete.

- The Runtime Acceptance workflow is green for the intended release commit.
- `PROJECT_STATUS.md` names the latest green run and its exact commit SHA.
- Functional, source-contract, timing, OCR-evaluation and UI exit codes are zero.
- The exact 50-ID frozen catalogue gate passes with no known gaps.
- Database migrations are sequential and exercised from an empty database.
- Dependency lockfiles and immutable container-image references are committed.
- Evidence limitations and pending features are stated without promotion to verified scope.

Feature commits may truthfully name the preceding green run while their own run
is pending. Before a release is cut, advance `PROJECT_STATUS.md` in a dedicated
baseline commit and obtain a green workflow for that commit.
