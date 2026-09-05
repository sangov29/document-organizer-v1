#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m py_compile acceptance/tests/conftest.py acceptance/tests/fixtures.py acceptance/tests/test_um_runtime.py acceptance/tests/test_di_runtime.py acceptance/tools/timing_probe.py acceptance/tools/sanitize_logs.py acceptance/tools/wait_for_stack.py
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path('acceptance/coverage-map.json').read_text())
expected = {f'UM-TC-{i:03d}' for i in range(1,6)} | {f'DI-TC-{i:03d}' for i in range(1,6)}
actual = set(m['tests'])
assert actual == expected, (expected - actual, actual - expected)
print('source-review checks passed: Python compile + exact 10-ID coverage map')
PY
