#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m py_compile acceptance/tests/conftest.py acceptance/tests/fixtures.py acceptance/tests/test_um_runtime.py acceptance/tests/test_di_runtime.py acceptance/tests/test_pp_runtime.py acceptance/tests/test_cr_runtime.py acceptance/tests/test_cl_ex_runtime.py acceptance/tests/test_cl_va_runtime.py acceptance/tests/test_pr_runtime.py acceptance/tests/test_sec_runtime.py acceptance/tests/test_in_runtime.py acceptance/tests/test_or_sr_runtime.py acceptance/tests/test_lifecycle_runtime.py acceptance/tools/timing_probe.py acceptance/tools/ocr_evaluation.py acceptance/tools/sanitize_logs.py acceptance/tools/wait_for_stack.py evaluation/bootstrap_corpus.py evaluation/intake_document.py evaluation/validate_corpus_manifest.py backend/app/api/auth.py backend/app/api/documents.py backend/app/api/shares.py backend/app/schemas/documents.py backend/app/workers/celery_app.py backend/alembic/versions/0008_classification_review.py backend/alembic/versions/0009_tags_collections.py backend/alembic/versions/0010_reminder_preferences.py backend/alembic/versions/0011_document_versions.py backend/alembic/versions/0012_share_links.py backend/tests/test_share_link_contracts.py backend/app/services/rate_limiter.py backend/app/services/ocr.py backend/app/services/analysis.py backend/app/services/sensitivity.py backend/app/services/reminders.py backend/app/services/file_validation.py
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path('acceptance/coverage-map.json').read_text())
frontend_package = json.loads(Path('frontend/package.json').read_text())
frontend_lock = json.loads(Path('frontend/package-lock.json').read_text())
ui_package = json.loads(Path('acceptance/ui/package.json').read_text())
ui_lock = json.loads(Path('acceptance/ui/package-lock.json').read_text())
frontend_dockerfile = Path('frontend/Dockerfile').read_text()
ui_dockerfile = Path('acceptance/ui/Dockerfile').read_text()
frontend_config = Path('frontend/next.config.mjs').read_text()
register_page = Path('frontend/app/register/page.tsx').read_text()
verify_page = Path('frontend/app/verify-email/page.tsx').read_text()
harness = Path('acceptance/run-local.sh').read_text()
project_status = Path('PROJECT_STATUS.md').read_text()
release_checklist = Path('docs/RELEASE_CHECKLIST.md').read_text()
expected = (
    {f'UM-TC-{i:03d}' for i in range(1,6)}
    | {f'DI-TC-{i:03d}' for i in range(1,6)}
    | {f'PP-TC-{i:03d}' for i in range(1,5)}
    | {'CR-TC-001', 'CR-TC-002'}
    | {f'CL-TC-{i:03d}' for i in range(1,6)}
    | {f'EX-TC-{i:03d}' for i in (1, 2, 3, 4, 5, 6, 7, 8, 9)}
    | {'PR-TC-001', 'PR-TC-002', 'PR-TC-003', 'PR-TC-004', 'PR-TC-005', 'PR-TC-006'}
    | {'SEC-TC-001'}
    | {'IN-TC-001', 'IN-TC-002'}
    | {f'OR-TC-{i:03d}' for i in range(1,5)}
    | {f'SR-TC-{i:03d}' for i in range(1,4)}
    | {f'VA-TC-{i:03d}' for i in range(1,5)}
)
actual = set(m['tests'])
assert actual == expected, (expected - actual, actual - expected)
assert frontend_package['dependencies']['next'] == '16.3.5'
assert frontend_lock['packages']['']['dependencies']['next'] == '16.3.5'
assert frontend_lock['packages']['node_modules/next']['version'] == '16.3.5'
assert ui_lock['packages']['']['devDependencies'] == ui_package['devDependencies']
assert ui_package['devDependencies']['@playwright/test'] == '1.63.0'
assert ui_lock['packages']['node_modules/@playwright/test']['version'] == '1.63.0'
assert 'mcr.microsoft.com/playwright:v1.63.0-noble' in ui_dockerfile
assert 'RUN npm ci' in frontend_dockerfile and 'RUN npm install' not in frontend_dockerfile
assert "allowedDevOrigins: ['frontend']" in frontend_config
assert 'disabled={!hydrated}' in register_page
assert 'const verificationStarted = useRef(false)' in verify_page
assert 'if (verificationStarted.current) return' in verify_page
assert 'verificationStarted.current = true' in verify_page
assert 'junit-source-contracts.xml' in harness
assert 'SOURCE_CONTRACT_EXIT -ne 0' in harness
assert 'Evidence: GitHub Runtime Acceptance #5 under the renamed workflow' in project_status
assert '`ecc3b71dbbe5d3563120e96b511f8a36653958e3`' in project_status
assert 'PROJECT_STATUS.md` names the latest green run' in release_checklist
print('source-review checks passed: Python compile + exact 50-ID coverage map')
PY
