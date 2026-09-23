from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[2]


def test_worker_mounts_ocr_evaluation_inputs_and_evidence_output():
    compose = (ROOT / "acceptance" / "docker-compose.acceptance.yml").read_text()
    worker = compose.split("  worker:\n", 1)[1].split("  ui-tests:\n", 1)[0]

    assert "./acceptance:/acceptance:ro" in worker
    assert ":/evidence" in worker
    assert "ACCEPTANCE_EVIDENCE_DIR_IN_CONTAINER: /evidence" in worker


def test_ui_journey_uses_accessible_labels_not_visual_placeholder_copy():
    journey = (
        ROOT / "acceptance" / "ui" / "tests" / "document-journey.spec.ts"
    ).read_text()

    assert "getByLabel('Email address')" in journey
    assert "getByLabel('Password')" in journey
    assert "getByPlaceholder('Email')" not in journey
    assert "getByPlaceholder('Password (12+ chars)')" not in journey
    assert "getByText('Canonical document')" in journey
    assert "getByText('Duplicate of')" not in journey
    assert "toContainText('Utility Bill')" in journey
    assert "toContainText('utility_bill')" not in journey


def test_minio_uses_official_registry_and_immutable_release():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z" in compose
    assert "minio/minio:latest" not in compose


def test_frontend_dependencies_are_patched_and_ui_install_is_reproducible():
    frontend_package = json.loads((ROOT / "frontend" / "package.json").read_text())
    frontend_lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    ui_dockerfile = (ROOT / "acceptance" / "ui" / "Dockerfile").read_text()
    ui_package = json.loads((ROOT / "acceptance" / "ui" / "package.json").read_text())
    ui_lock = json.loads((ROOT / "acceptance" / "ui" / "package-lock.json").read_text())
    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
    frontend_config = (ROOT / "frontend" / "next.config.mjs").read_text()
    register_page = (ROOT / "frontend" / "app" / "register" / "page.tsx").read_text()
    verify_page = (ROOT / "frontend" / "app" / "verify-email" / "page.tsx").read_text()

    assert frontend_package["dependencies"]["next"] == "16.3.5"
    assert frontend_lock["packages"]["node_modules/next"]["version"] == "16.3.5"
    assert "COPY package.json package-lock.json ./" in ui_dockerfile
    assert "RUN npm ci" in ui_dockerfile
    assert "RUN npm install" not in ui_dockerfile
    assert ui_package["devDependencies"]["@playwright/test"] == "1.63.0"
    assert ui_lock["packages"]["node_modules/@playwright/test"]["version"] == "1.63.0"
    assert "mcr.microsoft.com/playwright:v1.63.0-noble" in ui_dockerfile
    assert "RUN npm ci" in frontend_dockerfile
    assert "RUN npm install" not in frontend_dockerfile
    assert "allowedDevOrigins: ['frontend']" in frontend_config
    assert "disabled={!hydrated}" in register_page
    assert "useEffect(() => setHydrated(true), [])" in register_page
    assert "const verificationStarted = useRef(false)" in verify_page
    assert "if (verificationStarted.current) return" in verify_page
    assert "verificationStarted.current = true" in verify_page


def test_harness_executes_backend_source_contracts_as_a_mandatory_evidence_stream():
    harness = (ROOT / "acceptance" / "run-local.sh").read_text()

    assert "pytest -q tests" in harness
    assert "junit-source-contracts.xml" in harness
    assert 'SOURCE_CONTRACT_EXIT=${PIPESTATUS[0]}' in harness
    assert "SOURCE_CONTRACT_EXIT -ne 0" in harness


def test_timing_probe_uses_larger_sample_without_relaxing_security_tolerances():
    compose = (ROOT / "acceptance" / "docker-compose.acceptance.yml").read_text()
    probe = (ROOT / "acceptance" / "tools" / "timing_probe.py").read_text()

    assert 'TIMING_SAMPLES: ${TIMING_SAMPLES:-100}' in compose
    assert 'SAMPLES = int(os.getenv("TIMING_SAMPLES", "100"))' in probe
    assert 'MEDIAN_TOL = float(os.getenv("TIMING_MEDIAN_REL_TOL", "0.25"))' in probe
    assert 'P95_TOL = float(os.getenv("TIMING_P95_REL_TOL", "0.35"))' in probe
    assert 'KS_MAX = float(os.getenv("TIMING_KS_MAX", "0.35"))' in probe
