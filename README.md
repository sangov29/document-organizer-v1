# Intelligent Personal Document Organizer — V1

A containerized document-ingestion and analysis application with owner-scoped authentication, immutable storage, preprocessing, OCR, classification, structured extraction, provenance, human review, organization, search, export and sensitive-data controls.

## Verified baseline

GitHub Runtime Acceptance Run #31 is the current evidence baseline:

- **53/53 functional tests passed**
- **50 exact catalogue IDs covered**
- **3/3 timing probes passed**
- **1/1 Playwright browser journey passed**
- functional, timing and UI exit codes are all zero
- no known catalogue gaps reported by the harness

The frozen mapping is in `acceptance/coverage-map.json`. The reconstructed catalogue increment is documented in `docs/Test_Catalogue_v0.4_Reconstructed.md`.

## Capabilities

- Registration, verification, login, logout, password reset and optional TOTP
- Server-enforced Redis sessions and owner-scoped resource access
- PDF/JPG/PNG single and bulk ingestion
- Immutable MinIO objects, duplicate detection and explicit duplicate keep
- PDF page splitting, orientation correction, quality assessment and deskew
- Printed-text OCR with page/word lineage and bounding boxes
- Seven known document families plus explicit `unknown`
- Versioned predefined fields for Identity, Utility, Banking and Invoice/Receipt, plus generic Unknown fields, confidence, criticality and `not_found`
- Classification and field confirmation/correction with audit history
- Provenance linking classification and fields to documents, pages and regions
- Automatic organization, search, date sorting and pagination
- Stable JSON and normalized CSV export
- Default masking and audited reveal of financial fields and signatures

## Architecture

The local stack contains FastAPI, Celery, PostgreSQL, Redis, MinIO, Next.js and Mailpit. The data model contains 13 persisted domain entities. The Alembic migration chain is sequential from `0001` through `0008`.

## Local configuration

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the generated value as `TOTP_FERNET_KEY` in `.env`, then run:

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

Services:

- Frontend: http://localhost:3000
- API documentation: http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Validation

Run dependency-free/source contracts:

```bash
cd backend
python -m compileall -q app alembic tests
PYTHONPATH=. pytest -q tests
```

Run the full dependency-backed acceptance stack:

```bash
./acceptance/run-local.sh
```

Evidence is written to `acceptance/evidence/<run-id>/`, including functional, timing and UI JUnit, raw timing samples, sanitized logs, resource snapshots, machine-readable feature evidence and browser screenshots.

## Evidence limits

The acceptance suite uses deterministic synthetic fixtures. It proves the implemented V1 contracts; it does not claim corpus-wide AI accuracy, external email-provider delivery, production load/resilience, or unresolved policy periods such as retention.

See `PROJECT_STATUS.md` for the verified scope and proposed next catalogue increments.
