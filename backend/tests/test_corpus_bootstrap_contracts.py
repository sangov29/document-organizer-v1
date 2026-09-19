import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_corpus", ROOT / "evaluation" / "bootstrap_corpus.py"
)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_bootstrap_creates_hashed_draft_records(tmp_path):
    evaluation = tmp_path / "evaluation"
    private = evaluation / "private"
    private.mkdir(parents=True)
    (private / "identity.pdf").write_bytes(b"permission-cleared identity fixture")
    (private / "ignore.txt").write_text("not a supported document")

    manifest = bootstrap.build_manifest(evaluation / "corpus-manifest.json", private)

    assert manifest["schema_version"] == "corpus-manifest-v0.1"
    assert manifest["label_review"] == "draft"
    assert len(manifest["documents"]) == 1
    document = manifest["documents"][0]
    assert document["id"] == f"corpus-{document['sha256'][:12]}"
    assert document["source_path"] == "private/identity.pdf"
    assert document["consent_reference"] == "TODO"
    assert document["permission_basis"] == "TODO"
    assert document["source_provenance"] == "TODO"
    assert document["second_reviewer"] == "TODO"
    assert document["expected_family"] == "TODO"
    assert document["fields"] == []


def test_update_preserves_labels_and_tracks_renamed_content(tmp_path):
    evaluation = tmp_path / "evaluation"
    private = evaluation / "private"
    private.mkdir(parents=True)
    source = private / "original.png"
    source.write_bytes(b"permission-cleared labelled fixture")
    manifest_path = evaluation / "corpus-manifest.json"
    manifest = bootstrap.build_manifest(manifest_path, private)
    manifest["documents"][0].update({
        "consent_reference": "CONSENT-001",
        "expected_family": "identity",
        "fields": [{"field_name": "full_name", "value": "Example"}],
    })
    manifest["label_review"] = "two-reviewer-resolved"
    bootstrap.write_manifest(manifest_path, manifest)
    source.rename(private / "renamed.png")

    updated = bootstrap.build_manifest(manifest_path, private, update=True)

    document = updated["documents"][0]
    assert document["source_path"] == "private/renamed.png"
    assert document["consent_reference"] == "CONSENT-001"
    assert document["expected_family"] == "identity"
    assert document["fields"][0]["field_name"] == "full_name"
    assert updated["label_review"] == "two-reviewer-resolved"


def test_bootstrap_rejects_duplicate_content(tmp_path):
    evaluation = tmp_path / "evaluation"
    private = evaluation / "private"
    private.mkdir(parents=True)
    (private / "one.pdf").write_bytes(b"same content")
    (private / "two.png").write_bytes(b"same content")

    with pytest.raises(ValueError, match="duplicate content"):
        bootstrap.build_manifest(evaluation / "corpus-manifest.json", private)


def test_bootstrap_requires_manifest_sibling_private_directory(tmp_path):
    evaluation = tmp_path / "evaluation"
    private = tmp_path / "elsewhere"
    private.mkdir()

    with pytest.raises(ValueError, match="private directory must be"):
        bootstrap.build_manifest(evaluation / "corpus-manifest.json", private)
