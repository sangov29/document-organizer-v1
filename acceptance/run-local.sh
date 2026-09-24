#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ID="${ACCEPTANCE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 - <<'PY'
import secrets
print(secrets.token_hex(4))
PY
)}"
EVIDENCE_REL="acceptance/evidence/${RUN_ID}"
EVIDENCE_DIR="$ROOT/$EVIDENCE_REL"
GENERATED_ENV="$ROOT/acceptance/.env.acceptance.generated"
mkdir -p "$EVIDENCE_DIR/container-logs"

# Fresh synthetic secrets per run. Values are never printed.
python3 - "$GENERATED_ENV" <<'PY'
import base64, secrets, sys
from pathlib import Path
path = Path(sys.argv[1])
fernet = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
jwt = secrets.token_urlsafe(48)
path.write_text(f"""APP_ENV=acceptance
DATABASE_URL=postgresql+psycopg://docorganizer:docorganizer@postgres:5432/docorganizer
JWT_SECRET={jwt}
TOTP_FERNET_KEY={fernet}
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=documents
REDIS_URL=redis://redis:6379/0
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_STARTTLS=false
SMTP_FROM_EMAIL=no-reply@acceptance.invalid
MAX_UPLOAD_BYTES=1048576
IDLE_SESSION_MINUTES=1
VERIFICATION_TOKEN_MINUTES=5
PASSWORD_RESET_TOKEN_MINUTES=1
""")
PY
chmod 600 "$GENERATED_ENV"

export ACCEPTANCE_RUN_ID="$RUN_ID"
export ACCEPTANCE_EVIDENCE_DIR="./$EVIDENCE_REL"
export APP_ENV_FILE="acceptance/.env.acceptance.generated"

COMPOSE=(docker compose -f docker-compose.yml -f acceptance/docker-compose.acceptance.yml)

cleanup_logs() {
  local raw="$EVIDENCE_DIR/container-logs/raw.log"
  "${COMPOSE[@]}" logs --no-color backend worker postgres redis minio mailpit > "$raw" 2>&1 || true
  python3 acceptance/tools/sanitize_logs.py "$raw" "$EVIDENCE_DIR/container-logs/sanitized.log" || true
  rm -f "$raw"
  "${COMPOSE[@]}" ps > "$EVIDENCE_DIR/compose-ps.txt" 2>&1 || true
  rm -f "$GENERATED_ENV"
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}' > "$EVIDENCE_DIR/docker-stats.txt" 2>&1 || true
}
trap cleanup_logs EXIT

printf 'Acceptance run: %s\n' "$RUN_ID"
printf 'Evidence: %s\n' "$EVIDENCE_REL"

# Repeatability: each run starts from empty DB/Redis/object-storage/mail state.
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true

# Bring dependencies up first to avoid storage/mail startup races.
"${COMPOSE[@]}" up -d postgres redis minio mailpit
python3 - <<'PY'
import time, urllib.request
checks = ["http://localhost:9000/minio/health/live", "http://localhost:8025/api/v1/"]
for url in checks:
    deadline = time.time() + 90
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    break
        except Exception as exc:
            last = exc
        time.sleep(1)
    else:
        raise SystemExit(f"dependency health timeout for {url}: {last!r}")
PY

"${COMPOSE[@]}" up -d --build backend
# Apply schema before worker can receive any acceptance jobs.
"${COMPOSE[@]}" exec -T backend alembic upgrade head
"${COMPOSE[@]}" up -d worker frontend

python3 - <<'PY'
import time, urllib.request
url = "http://localhost:8000/health"
deadline = time.time() + 90
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            if r.status == 200:
                break
    except Exception as exc:
        last = exc
    time.sleep(1)
else:
    raise SystemExit(f"backend health timeout: {last!r}")
PY

set +e
"${COMPOSE[@]}" run --rm -T \
  -v "$ROOT:/repo:ro" -w /repo/backend backend \
  env PYTHONPATH=/repo/backend pytest -q tests \
  --junitxml=/evidence/junit-source-contracts.xml 2>&1 | tee "$EVIDENCE_DIR/source-contract-output.txt"
SOURCE_CONTRACT_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T backend \
  env PYTHONPATH=/app pytest -c /acceptance/pytest.ini /acceptance/tests \
  --junitxml=/evidence/junit-functional.xml -q -x 2>&1 | tee "$EVIDENCE_DIR/pytest-output.txt"
FUNCTIONAL_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T backend \
  python /acceptance/tools/timing_probe.py 2>&1 | tee "$EVIDENCE_DIR/timing-output.txt"
TIMING_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T worker \
  env PYTHONPATH=/app python /acceptance/tools/ocr_evaluation.py \
  2>&1 | tee "$EVIDENCE_DIR/ocr-evaluation-output.txt"
OCR_EVAL_EXIT=${PIPESTATUS[0]}

python3 - <<'PY'
import time, urllib.request
url = "http://localhost:3000"
deadline = time.time() + 90
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status == 200:
                break
    except Exception as exc:
        last = exc
    time.sleep(1)
else:
    raise SystemExit(f"frontend health timeout: {last!r}")
PY

"${COMPOSE[@]}" --profile acceptance-ui run --rm --build ui-tests \
  2>&1 | tee "$EVIDENCE_DIR/ui-output.txt"
UI_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T backend \
  python /acceptance/tools/load_qualification.py 2>&1 | tee "$EVIDENCE_DIR/load-qualification-output.txt"
LOAD_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T backend \
  python /acceptance/tools/write_ocr_qualification.py 2>&1 | tee "$EVIDENCE_DIR/write-ocr-qualification-output.txt"
WRITE_OCR_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T backend \
  python /acceptance/tools/slo_evaluation.py 2>&1 | tee "$EVIDENCE_DIR/slo-evaluation-output.txt"
SLO_EXIT=${PIPESTATUS[0]}
set -e

# Snapshot and restore into disposable database/bucket targets after the
# functional suite has produced real synthetic document rows and objects.
# The probe writes only digests/counts; snapshot bytes remain temporary.
BACKUP_RESTORE_EXIT=1
if [[ $FUNCTIONAL_EXIT -eq 0 ]]; then
  set +e
  python3 acceptance/tools/backup_restore_probe.py \
    "$EVIDENCE_DIR/backup-restore.json" 2>&1 | tee "$EVIDENCE_DIR/backup-restore-output.txt"
  BACKUP_RESTORE_EXIT=${PIPESTATUS[0]}
  set -e
fi

cat > "$EVIDENCE_DIR/run-summary.json" <<JSON
{
  "run_id": "$RUN_ID",
  "source_contract_exit": $SOURCE_CONTRACT_EXIT,
  "functional_exit": $FUNCTIONAL_EXIT,
  "timing_exit": $TIMING_EXIT,
  "ocr_evaluation_exit": $OCR_EVAL_EXIT,
  "ui_exit": $UI_EXIT,
  "load_exit": $LOAD_EXIT,
  "write_ocr_exit": $WRITE_OCR_EXIT,
  "slo_exit": $SLO_EXIT,
  "backup_restore_exit": $BACKUP_RESTORE_EXIT,
  "backup_restore_json": "backup-restore.json",
  "functional_junit": "junit-functional.xml",
  "timing_json": "timing.json",
  "timing_junit": "junit-timing.xml",
  "ocr_evaluation_json": "ocr-evaluation.json",
  "ocr_evaluation_junit": "junit-ocr-evaluation.xml",
  "ui_junit": "junit-ui.xml",
  "load_qualification_json": "load-qualification.json",
  "load_junit": "junit-load.xml",
  "write_ocr_qualification_json": "write-ocr-qualification.json",
  "write_ocr_junit": "junit-write-ocr.xml",
  "slo_evaluation_json": "slo-evaluation.json",
  "slo_junit": "junit-slo.xml",
  "source_contract_junit": "junit-source-contracts.xml",
  "known_catalogue_gaps": [],
  "mail_scope": "local Mailpit queue/token/sink lifecycle only; no external provider claim"
}
JSON

printf '\nFunctional acceptance exit: %s\n' "$FUNCTIONAL_EXIT"
printf 'Source/model contract exit: %s\n' "$SOURCE_CONTRACT_EXIT"
printf 'Timing evidence exit: %s\n' "$TIMING_EXIT"
printf 'OCR evaluation exit: %s\n' "$OCR_EVAL_EXIT"
printf 'UI acceptance exit: %s\n' "$UI_EXIT"
printf 'Load qualification exit: %s\n' "$LOAD_EXIT"
printf 'Write/OCR qualification exit: %s\n' "$WRITE_OCR_EXIT"
printf 'SLO evaluation exit: %s\n' "$SLO_EXIT"
printf 'Backup/restore probe exit: %s\n' "$BACKUP_RESTORE_EXIT"
printf 'Evidence directory: %s\n' "$EVIDENCE_REL"

# Timing is intentionally separate, but the one-command harness is considered
# unsuccessful if either evidence stream fails its own acceptance rule.
if [[ $SOURCE_CONTRACT_EXIT -ne 0 || $FUNCTIONAL_EXIT -ne 0 || $TIMING_EXIT -ne 0 || $OCR_EVAL_EXIT -ne 0 || $UI_EXIT -ne 0 || $LOAD_EXIT -ne 0 || $WRITE_OCR_EXIT -ne 0 || $SLO_EXIT -ne 0 || $BACKUP_RESTORE_EXIT -ne 0 ]]; then
  exit 1
fi
