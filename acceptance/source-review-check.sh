#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m py_compile acceptance/tests/conftest.py acceptance/tests/fixtures.py acceptance/tests/test_um_runtime.py acceptance/tests/test_di_runtime.py acceptance/tests/test_pp_runtime.py acceptance/tests/test_cr_runtime.py acceptance/tests/test_cl_ex_runtime.py acceptance/tests/test_pr_runtime.py acceptance/tests/test_sec_runtime.py acceptance/tools/timing_probe.py acceptance/tools/sanitize_logs.py acceptance/tools/wait_for_stack.py backend/app/services/ocr.py backend/app/services/analysis.py backend/app/services/sensitivity.py
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path('acceptance/coverage-map.json').read_text())
expected = (
    {f'UM-TC-{i:03d}' for i in range(1,6)}
    | {f'DI-TC-{i:03d}' for i in range(1,6)}
    | {f'PP-TC-{i:03d}' for i in range(1,5)}
    | {'CR-TC-001'}
    | {'CL-TC-001', 'EX-TC-008', 'EX-TC-009'}
    | {'PR-TC-004'}
    | {'SEC-TC-001'}
)
actual = set(m['tests'])
assert actual == expected, (expected - actual, actual - expected)
print('source-review checks passed: Python compile + exact 20-ID coverage map')
PY
