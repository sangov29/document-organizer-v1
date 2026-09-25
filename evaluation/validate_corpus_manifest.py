#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


FAMILIES = {"identity", "utility", "banking", "educational", "employment", "invoice_receipt", "travel", "unknown"}
OUT_OF_FAMILY_KINDS = {"certificate", "resume_cv", "plane_ticket", "boarding_pass", "other"}
REQUIRED_OUT_OF_FAMILY_KINDS = {"certificate", "resume_cv", "plane_ticket", "boarding_pass"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PERMISSION_BASES = {"owner_document", "written_consent", "realistic_synthetic", "public_domain"}
PLACEHOLDERS = {"", "tbd", "todo", "reviewer", "me", "n/a", "na", "test", "unknown", "pending"}
AXIS_ORDER = ("family", "unknown_status", "presence", "value", "page", "region")


def _identity(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if normalized.casefold() in PLACEHOLDERS or len(normalized) < 3:
        return None
    return normalized


def _field_map(label: dict) -> dict[str, dict]:
    fields = label.get("fields")
    if not isinstance(fields, list):
        return {}
    return {
        field["field_name"]: field
        for field in fields
        if isinstance(field, dict) and isinstance(field.get("field_name"), str)
    }


def _disagreement_axes(label_a: dict, label_b: dict) -> list[str]:
    axes: set[str] = set()
    family_a = label_a.get("expected_family")
    family_b = label_b.get("expected_family")
    if family_a != family_b:
        axes.add("family")
    if (family_a == "unknown") != (family_b == "unknown"):
        axes.add("unknown_status")
    elif family_a == family_b == "unknown" and (
        label_a.get("out_of_family_kind") != label_b.get("out_of_family_kind")
    ):
        axes.add("unknown_status")
    fields_a = _field_map(label_a)
    fields_b = _field_map(label_b)
    if set(fields_a) != set(fields_b):
        axes.add("presence")
    for name in set(fields_a) & set(fields_b):
        if fields_a[name].get("value") != fields_b[name].get("value"):
            axes.add("value")
        if fields_a[name].get("page_number") != fields_b[name].get("page_number"):
            axes.add("page")
        if fields_a[name].get("bbox") != fields_b[name].get("bbox"):
            axes.add("region")
    return [axis for axis in AXIS_ORDER if axis in axes]


def _label_projection(document: dict) -> dict:
    projected = {
        "expected_family": document.get("expected_family"),
        "fields": document.get("fields"),
    }
    if document.get("expected_family") == "unknown":
        projected["out_of_family_kind"] = document.get("out_of_family_kind")
    return projected


def _canonical_label(label: dict) -> dict:
    canonical = {
        "expected_family": label.get("expected_family"),
        "fields": sorted(
            (item for item in label.get("fields", []) if isinstance(item, dict)),
            key=lambda field: field.get("field_name", ""),
        ),
    }
    if label.get("expected_family") == "unknown":
        canonical["out_of_family_kind"] = label.get("out_of_family_kind")
    return canonical


def _valid_label_evidence(label: dict) -> bool:
    family = label.get("expected_family")
    if family not in FAMILIES:
        return False
    if family == "unknown" and label.get("out_of_family_kind") not in OUT_OF_FAMILY_KINDS:
        return False
    fields = label.get("fields")
    if not isinstance(fields, list):
        return False
    names: set[str] = set()
    for field in fields:
        if not isinstance(field, dict) or not isinstance(field.get("field_name"), str):
            return False
        if not field["field_name"] or field["field_name"] in names or "value" not in field:
            return False
        names.add(field["field_name"])
        if not isinstance(field.get("page_number"), int) or field["page_number"] < 1:
            return False
        bbox = field.get("bbox")
        if not isinstance(bbox, dict) or set(bbox) != {"x", "y", "width", "height"}:
            return False
        if any(not isinstance(value, int) or value < 0 for value in bbox.values()):
            return False
        if bbox["width"] < 1 or bbox["height"] < 1:
            return False
    return True


def _validate_reviewer_evidence(document: dict, prefix: str, errors: list[str]) -> None:
    reviewer_a = _identity(document.get("reviewer_a"))
    reviewer_b = _identity(document.get("reviewer_b"))
    if reviewer_a is None:
        errors.append(f"{prefix}.reviewer_a must be a non-placeholder reviewer identity")
    if reviewer_b is None:
        errors.append(f"{prefix}.reviewer_b must be a non-placeholder reviewer identity")
    if reviewer_a and reviewer_b and reviewer_a.casefold() == reviewer_b.casefold():
        errors.append(f"{prefix}.reviewer_a and reviewer_b must be distinct")

    label_a = document.get("reviewer_a_label")
    label_b = document.get("reviewer_b_label")
    if not isinstance(label_a, dict):
        errors.append(f"{prefix}.reviewer_a_label must contain independent label evidence")
    if not isinstance(label_b, dict):
        errors.append(f"{prefix}.reviewer_b_label must contain independent label evidence")
    if not isinstance(label_a, dict) or not isinstance(label_b, dict):
        return
    if not _valid_label_evidence(label_a):
        errors.append(f"{prefix}.reviewer_a_label is not complete label evidence")
    if not _valid_label_evidence(label_b):
        errors.append(f"{prefix}.reviewer_b_label is not complete label evidence")

    axes = _disagreement_axes(label_a, label_b)
    agreement = not axes
    if document.get("reviewer_agreement") is not agreement:
        errors.append(f"{prefix}.reviewer_agreement must equal the validator-derived value {agreement}")
    declared_axes = document.get("disagreement_axes")
    if declared_axes != axes:
        errors.append(f"{prefix}.disagreement_axes must equal validator-derived axes {axes}")

    final_label = _label_projection(document)
    if agreement:
        if _canonical_label(label_a) != _canonical_label(final_label):
            errors.append(f"{prefix} resolved label must equal the independently agreed reviewer label")
        if document.get("adjudication_mode") not in (None, ""):
            errors.append(f"{prefix}.adjudication_mode must be empty when reviewers agree")
        return

    mode = document.get("adjudication_mode")
    if mode == "unresolved":
        errors.append(f"{prefix} reviewer disagreement remains unresolved")
        return
    if mode not in {"joint", "third_party"}:
        errors.append(f"{prefix}.adjudication_mode must be joint or third_party for disagreements")
    adjudicator = document.get("adjudicator")
    if mode == "joint":
        if not isinstance(adjudicator, list) or {
            _identity(value) for value in adjudicator
        } != {reviewer_a, reviewer_b}:
            errors.append(f"{prefix}.adjudicator must list both reviewers for joint adjudication")
    elif mode == "third_party":
        third_party = _identity(adjudicator)
        if third_party is None or third_party.casefold() in {
            reviewer_a.casefold() if reviewer_a else "",
            reviewer_b.casefold() if reviewer_b else "",
        }:
            errors.append(f"{prefix}.adjudicator must be an independent third-party identity")
    adjudicated_label = document.get("adjudicated_label")
    if not isinstance(adjudicated_label, dict) or (
        _canonical_label(adjudicated_label) != _canonical_label(final_label)
    ):
        errors.append(f"{prefix}.adjudicated_label must equal the resolved manifest label")
    rationale = document.get("adjudication_rationale")
    if not isinstance(rationale, str) or rationale.strip().casefold() in PLACEHOLDERS:
        errors.append(f"{prefix}.adjudication_rationale is required for disagreements")


def validate(manifest: dict, root: Path, verify_files: bool, mode: str) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "corpus-manifest-v0.2":
        errors.append("schema_version must be corpus-manifest-v0.2")
    if manifest.get("label_review") != "two-reviewer-resolved":
        errors.append("label_review must be two-reviewer-resolved")
    documents = manifest.get("documents")
    if not isinstance(documents, list):
        return [*errors, "documents must be an array"]
    minimum = 30 if mode == "pilot" else 100
    if len(documents) < minimum:
        errors.append(f"{mode} corpus requires at least {minimum} documents")
    ids: set[str] = set()
    families: Counter[str] = Counter()
    unknown_kinds: Counter[str] = Counter()
    for index, document in enumerate(documents):
        prefix = f"documents[{index}]"
        document_id = document.get("id")
        if not isinstance(document_id, str) or not document_id:
            errors.append(f"{prefix}.id is required")
        elif document_id in ids:
            errors.append(f"{prefix}.id is duplicated")
        else:
            ids.add(document_id)
        family = document.get("expected_family")
        if family not in FAMILIES:
            errors.append(f"{prefix}.expected_family is invalid")
        else:
            families[family] += 1
        if family == "unknown":
            kind = document.get("out_of_family_kind")
            if kind not in OUT_OF_FAMILY_KINDS:
                errors.append(f"{prefix}.out_of_family_kind is required for unknown documents")
            else:
                unknown_kinds[kind] += 1
        source = document.get("source_path")
        if not isinstance(source, str) or not source.startswith("private/") or ".." in Path(source).parts:
            errors.append(f"{prefix}.source_path must be a safe relative path under private/")
        digest = document.get("sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            errors.append(f"{prefix}.sha256 must be 64 lowercase hexadecimal characters")
        if not document.get("consent_reference"):
            errors.append(f"{prefix}.consent_reference is required")
        if document.get("permission_basis") not in PERMISSION_BASES:
            errors.append(f"{prefix}.permission_basis is invalid")
        if not document.get("source_provenance"):
            errors.append(f"{prefix}.source_provenance is required")
        _validate_reviewer_evidence(document, prefix, errors)
        fields = document.get("fields")
        if not isinstance(fields, list):
            errors.append(f"{prefix}.fields must be an array")
            continue
        for field_index, field in enumerate(fields):
            field_prefix = f"{prefix}.fields[{field_index}]"
            if not field.get("field_name") or "value" not in field:
                errors.append(f"{field_prefix} requires field_name and value")
            if not isinstance(field.get("page_number"), int) or field["page_number"] < 1:
                errors.append(f"{field_prefix}.page_number must be a positive integer")
            bbox = field.get("bbox")
            if not isinstance(bbox, dict) or set(bbox) != {"x", "y", "width", "height"}:
                errors.append(f"{field_prefix}.bbox must contain x, y, width and height")
            elif any(not isinstance(value, int) or value < 0 for value in bbox.values()) or bbox["width"] < 1 or bbox["height"] < 1:
                errors.append(f"{field_prefix}.bbox coordinates must be non-negative with positive size")
        if verify_files and isinstance(source, str):
            path = root / source
            if not path.is_file():
                errors.append(f"{prefix}.source_path does not exist")
            elif SHA256.fullmatch(str(digest)) and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                errors.append(f"{prefix}.sha256 does not match the source file")
    if mode == "adoption":
        for family in sorted(FAMILIES - {"unknown"}):
            if families[family] < 10:
                errors.append(f"adoption corpus requires at least 10 {family} documents")
        if families["unknown"] < 20:
            errors.append("adoption corpus requires at least 20 unknown documents")
    else:
        if families["unknown"] < 8:
            errors.append("pilot corpus requires at least 8 unknown documents")
        for kind in sorted(REQUIRED_OUT_OF_FAMILY_KINDS):
            if unknown_kinds[kind] < 2:
                errors.append(f"pilot corpus requires at least 2 unknown {kind} documents")
    if not (REQUIRED_OUT_OF_FAMILY_KINDS <= set(unknown_kinds)):
        errors.append("unknown corpus must cover certificate, resume_cv, plane_ticket and boarding_pass")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a private OCR evaluation corpus manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--mode", choices=("pilot", "adoption"), default="pilot")
    parser.add_argument("--verify-files", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    errors = validate(manifest, args.manifest.parent, args.verify_files, args.mode)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Corpus manifest valid for {args.mode}: {len(manifest['documents'])} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
