#!/usr/bin/env python3
"""Intake exactly one permission-cleared document into the private corpus."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from bootstrap_corpus import SUPPORTED_SUFFIXES, build_manifest, sha256_file, write_manifest


PERMISSION_BASES = ("owner_document", "written_consent", "realistic_synthetic", "public_domain")


def intake(source: Path, manifest_path: Path, permission_basis: str, provenance: str, second_reviewer: str) -> dict:
    source = source.resolve()
    manifest_path = manifest_path.resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("source must be a regular file")
    if source.suffix.casefold() not in SUPPORTED_SUFFIXES:
        raise ValueError("source must be PDF, JPG, JPEG or PNG")
    if permission_basis not in PERMISSION_BASES:
        raise ValueError("unsupported permission basis")
    if not provenance.strip() or not second_reviewer.strip():
        raise ValueError("source provenance and second reviewer are required")

    private_dir = manifest_path.parent / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(source)
    existing = list(private_dir.glob(f"{digest[:16]}-*"))
    if existing:
        raise ValueError(f"duplicate content already present: {existing[0].name}")
    destination = private_dir / f"{digest[:16]}-{source.name}"
    shutil.copyfile(source, destination)

    manifest = build_manifest(manifest_path, private_dir, update=manifest_path.exists())
    record = next(item for item in manifest["documents"] if item["sha256"] == digest)
    record.update({
        "permission_basis": permission_basis,
        "consent_reference": permission_basis,
        "source_provenance": provenance.strip(),
        "second_reviewer": second_reviewer.strip(),
    })
    write_manifest(manifest_path, manifest)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("evaluation/corpus-manifest.json"))
    parser.add_argument("--permission-basis", choices=PERMISSION_BASES, required=True)
    parser.add_argument("--provenance", required=True, help="Non-sensitive description of where the source came from")
    parser.add_argument("--second-reviewer", required=True)
    args = parser.parse_args()
    try:
        record = intake(args.source, args.manifest, args.permission_basis, args.provenance, args.second_reviewer)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"id": record["id"], "sha256": record["sha256"], "source_path": record["source_path"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
