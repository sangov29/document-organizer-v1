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
"${COMPOSE[@]}" exec -T backend \
  env PYTHONPATH=/app pytest -c /acceptance/pytest.ini /acceptance/tests \
  --junitxml=/evidence/junit-functional.xml -q 2>&1 | tee "$EVIDENCE_DIR/pytest-output.txt"
FUNCTIONAL_EXIT=${PIPESTATUS[0]}

"${COMPOSE[@]}" exec -T backend \
  python /acceptance/tools/timing_probe.py 2>&1 | tee "$EVIDENCE_DIR/timing-output.txt"
TIMING_EXIT=${PIPESTATUS[0]}
set -e

cat > "$EVIDENCE_DIR/run-summary.json" <<JSON
{
  "run_id": "$RUN_ID",
  "functional_exit": $FUNCTIONAL_EXIT,
  "timing_exit": $TIMING_EXIT,
  "functional_junit": "junit-functional.xml",
  "timing_json": "timing.json",
  "timing_junit": "junit-timing.xml",
  "known_catalogue_gaps": [
    "UM-TC-002 steps 5-6: no public resource-by-ID endpoint",
    "DI-TC-002 step 5: no public duplicate proceed/keep override"
  ],
  "mail_scope": "local Mailpit queue/token/sink lifecycle only; no external provider claim"
}
JSON

printf '\nFunctional acceptance exit: %s\n' "$FUNCTIONAL_EXIT"
printf 'Timing evidence exit: %s\n' "$TIMING_EXIT"
printf 'Evidence directory: %s\n' "$EVIDENCE_REL"

# Timing is intentionally separate, but the one-command harness is considered
# unsuccessful if either evidence stream fails its own acceptance rule.
if [[ $FUNCTIONAL_EXIT -ne 0 || $TIMING_EXIT -ne 0 ]]; then
  exit 1
fi
