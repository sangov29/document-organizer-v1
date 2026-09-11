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


def validate(manifest: dict, root: Path, verify_files: bool, mode: str) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "corpus-manifest-v0.1":
        errors.append("schema_version must be corpus-manifest-v0.1")
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
