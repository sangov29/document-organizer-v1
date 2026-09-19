import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_intake_accepts_one_document_and_rejects_duplicate(tmp_path):
    source = tmp_path / "phone-photo.jpg"
    source.write_bytes(b"permission-cleared realistic phone photograph")
    manifest = tmp_path / "evaluation" / "corpus-manifest.json"
    command = [
        sys.executable, str(ROOT / "evaluation" / "intake_document.py"), str(source),
        "--manifest", str(manifest), "--permission-basis", "owner_document",
        "--provenance", "Owner supplied phone photograph", "--second-reviewer", "reviewer-b",
    ]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert manifest.is_file()
    private_files = list((manifest.parent / "private").iterdir())
    assert len(private_files) == 1

    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 1
    assert "duplicate content already present" in second.stderr


def test_intake_requires_permission_provenance_and_reviewer_contract():
    source = (ROOT / "evaluation" / "intake_document.py").read_text()
    assert '"owner_document"' in source and '"written_consent"' in source
    assert '"realistic_synthetic"' in source and '"public_domain"' in source
    assert 'parser.add_argument("--provenance", required=True' in source
    assert 'parser.add_argument("--second-reviewer", required=True' in source
