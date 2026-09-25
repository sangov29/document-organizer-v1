import importlib.util
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "validate_corpus_manifest", ROOT / "evaluation" / "validate_corpus_manifest.py"
)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _document(index: int, family: str, kind: str | None = None) -> dict:
    document = {
        "id": f"sample-{index:03d}",
        "source_path": f"private/sample-{index:03d}.pdf",
        "sha256": f"{index:064x}",
        "consent_reference": f"consent-{index:03d}",
        "permission_basis": "written_consent",
        "source_provenance": f"internal-source-{index:03d}",
        "reviewer_a": "reviewer-a",
        "reviewer_b": "reviewer-b",
        "expected_family": family,
        "fields": [
            {
                "field_name": "reference",
                "value": f"REF-{index:03d}",
                "page_number": 1,
                "bbox": {"x": 10, "y": 20, "width": 100, "height": 20},
                "sensitive": False,
            }
        ],
    }
    if kind:
        document["out_of_family_kind"] = kind
    agreed_label = {
        "expected_family": family,
        "fields": deepcopy(document["fields"]),
    }
    if kind:
        agreed_label["out_of_family_kind"] = kind
    document.update({
        "reviewer_a_label": deepcopy(agreed_label),
        "reviewer_b_label": deepcopy(agreed_label),
        "reviewer_agreement": True,
        "disagreement_axes": [],
        "adjudicator": None,
        "adjudication_mode": None,
        "adjudicated_label": None,
        "adjudication_rationale": None,
    })
    return document


def _manifest(documents: list[dict]) -> dict:
    return {
        "schema_version": "corpus-manifest-v0.2",
        "label_review": "two-reviewer-resolved",
        "documents": documents,
    }


def _valid_pilot() -> dict:
    documents = [_document(i, "identity") for i in range(22)]
    kinds = ("certificate", "resume_cv", "plane_ticket", "boarding_pass")
    documents.extend(
        _document(22 + i, "unknown", kinds[i // 2]) for i in range(8)
    )
    return _manifest(documents)


def test_pilot_requires_real_out_of_family_coverage():
    manifest = _valid_pilot()
    assert validator.validate(manifest, ROOT / "evaluation", False, "pilot") == []

    manifest["documents"][-1]["out_of_family_kind"] = "other"
    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")
    assert "pilot corpus requires at least 2 unknown boarding_pass documents" in errors


def test_adoption_requires_family_and_unknown_distribution():
    families = sorted(validator.FAMILIES - {"unknown"})
    documents = []
    index = 0
    for family in families:
        documents.extend(_document(index + offset, family) for offset in range(10))
        index += 10
    kinds = ("certificate", "resume_cv", "plane_ticket", "boarding_pass")
    documents.extend(
        _document(index + offset, "unknown", kinds[offset % len(kinds)])
        for offset in range(20)
    )
    index += 20
    documents.extend(_document(index + offset, "identity") for offset in range(10))
    manifest = _manifest(documents)
    assert validator.validate(manifest, ROOT / "evaluation", False, "adoption") == []

    manifest["documents"] = manifest["documents"][:-11]
    errors = validator.validate(manifest, ROOT / "evaluation", False, "adoption")
    assert "adoption corpus requires at least 100 documents" in errors
    assert "adoption corpus requires at least 20 unknown documents" in errors


def test_manifest_rejects_path_traversal_and_bad_digest():
    manifest = _valid_pilot()
    manifest["documents"][0]["source_path"] = "private/../secret.pdf"
    manifest["documents"][0]["sha256"] = "NOT-A-DIGEST"
    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")
    assert "documents[0].source_path must be a safe relative path under private/" in errors
    assert "documents[0].sha256 must be 64 lowercase hexadecimal characters" in errors


def test_two_reviewer_claim_without_evidence_is_rejected():
    manifest = _valid_pilot()
    document = manifest["documents"][0]
    for key in (
        "reviewer_a", "reviewer_b", "reviewer_a_label", "reviewer_b_label",
        "reviewer_agreement", "disagreement_axes", "adjudicator",
        "adjudication_mode", "adjudicated_label", "adjudication_rationale",
    ):
        document.pop(key, None)
    document["second_reviewer"] = "reviewer-b"

    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")

    assert "documents[0].reviewer_a must be a non-placeholder reviewer identity" in errors
    assert "documents[0].reviewer_b must be a non-placeholder reviewer identity" in errors
    assert "documents[0].reviewer_a_label must contain independent label evidence" in errors
    assert "documents[0].reviewer_b_label must contain independent label evidence" in errors


def test_reviewer_agreement_and_axes_are_derived_not_trusted():
    manifest = _valid_pilot()
    document = manifest["documents"][0]
    document["reviewer_b_label"]["fields"][0]["value"] = "DIFFERENT"
    document["reviewer_agreement"] = True
    document["disagreement_axes"] = []

    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")

    assert "documents[0].reviewer_agreement must equal the validator-derived value False" in errors
    assert "documents[0].disagreement_axes must equal validator-derived axes ['value']" in errors


def test_disagreement_requires_resolved_independent_adjudication():
    manifest = _valid_pilot()
    document = manifest["documents"][0]
    document["reviewer_b_label"]["fields"][0]["value"] = "DIFFERENT"
    document.update({
        "reviewer_agreement": False,
        "disagreement_axes": ["value"],
        "adjudication_mode": "third_party",
        "adjudicator": "reviewer-c",
        "adjudicated_label": {
            "expected_family": document["expected_family"],
            "fields": deepcopy(document["fields"]),
        },
        "adjudication_rationale": "Source region clearly supports Reviewer A's transcription.",
    })
    assert validator.validate(manifest, ROOT / "evaluation", False, "pilot") == []

    document["adjudicator"] = "reviewer-a"
    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")
    assert "documents[0].adjudicator must be an independent third-party identity" in errors

    document["adjudicator"] = "reviewer-c"
    document["adjudication_mode"] = "unresolved"
    errors = validator.validate(manifest, ROOT / "evaluation", False, "adoption")
    assert "documents[0] reviewer disagreement remains unresolved" in errors


def test_reviewer_identities_must_be_distinct_and_non_placeholder():
    manifest = _valid_pilot()
    document = manifest["documents"][0]
    document["reviewer_a"] = "TBD"
    document["reviewer_b"] = "TBD"
    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")
    assert "documents[0].reviewer_a must be a non-placeholder reviewer identity" in errors
    assert "documents[0].reviewer_b must be a non-placeholder reviewer identity" in errors

    document["reviewer_a"] = "same-person"
    document["reviewer_b"] = "SAME-PERSON"
    errors = validator.validate(manifest, ROOT / "evaluation", False, "pilot")
    assert "documents[0].reviewer_a and reviewer_b must be distinct" in errors
