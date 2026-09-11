#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m py_compile acceptance/tests/conftest.py acceptance/tests/fixtures.py acceptance/tests/test_um_runtime.py acceptance/tests/test_di_runtime.py acceptance/tests/test_pp_runtime.py acceptance/tests/test_cr_runtime.py acceptance/tests/test_cl_ex_runtime.py acceptance/tests/test_cl_va_runtime.py acceptance/tests/test_pr_runtime.py acceptance/tests/test_sec_runtime.py acceptance/tests/test_in_runtime.py acceptance/tests/test_or_sr_runtime.py acceptance/tests/test_lifecycle_runtime.py acceptance/tools/timing_probe.py acceptance/tools/ocr_evaluation.py acceptance/tools/sanitize_logs.py acceptance/tools/wait_for_stack.py backend/app/api/documents.py backend/app/schemas/documents.py backend/app/workers/celery_app.py backend/alembic/versions/0008_classification_review.py backend/app/services/ocr.py backend/app/services/analysis.py backend/app/services/sensitivity.py
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path('acceptance/coverage-map.json').read_text())
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
print('source-review checks passed: Python compile + exact 50-ID coverage map')
PY
