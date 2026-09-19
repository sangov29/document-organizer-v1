#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(private_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in private_dir.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.casefold() in SUPPORTED_SUFFIXES
    )


def _safe_source_path(path: Path, manifest_dir: Path) -> str:
    resolved = path.resolve()
    private_root = (manifest_dir / "private").resolve()
    try:
        resolved.relative_to(private_root)
    except ValueError as exc:
        raise ValueError(f"source file must be under {private_root}: {resolved}") from exc
    return resolved.relative_to(manifest_dir.resolve()).as_posix()


def build_manifest(manifest_path: Path, private_dir: Path, update: bool = False) -> dict:
    manifest_path = manifest_path.resolve()
    private_dir = private_dir.resolve()
    expected_private = (manifest_path.parent / "private").resolve()
    if private_dir != expected_private:
        raise ValueError(f"private directory must be {expected_private}")
    if not private_dir.is_dir():
        raise ValueError(f"private directory does not exist: {private_dir}")
    if manifest_path.exists() and not update:
        raise ValueError(f"manifest already exists; use --update: {manifest_path}")

    existing = {}
    label_review = "draft"
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text())
        if loaded.get("schema_version") != "corpus-manifest-v0.1":
            raise ValueError("existing manifest schema_version must be corpus-manifest-v0.1")
        for document in loaded.get("documents", []):
            digest = document.get("sha256")
            if isinstance(digest, str):
                existing[digest] = document
        label_review = loaded.get("label_review", "draft")

    documents = []
    seen: dict[str, Path] = {}
    for path in source_files(private_dir):
        digest = sha256_file(path)
        if digest in seen:
            raise ValueError(f"duplicate content: {seen[digest]} and {path}")
        seen[digest] = path
        relative = _safe_source_path(path, manifest_path.parent)
        if digest in existing:
            document = dict(existing[digest])
            document["source_path"] = relative
        else:
            document = {
                "id": f"corpus-{digest[:12]}",
                "source_path": relative,
                "sha256": digest,
                "consent_reference": "TODO",
                "permission_basis": "TODO",
                "source_provenance": "TODO",
                "second_reviewer": "TODO",
                "expected_family": "TODO",
                "fields": [],
            }
        documents.append(document)

    if update:
        for digest, document in existing.items():
            if digest not in seen:
                documents.append(document)

    return {
        "schema_version": "corpus-manifest-v0.1",
        "label_review": label_review,
        "documents": sorted(documents, key=lambda item: item["id"]),
    }


def write_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_name(f".{manifest_path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(manifest_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update a private document-intelligence corpus manifest"
    )
    parser.add_argument(
        "manifest", nargs="?", type=Path, default=Path("evaluation/corpus-manifest.json")
    )
    parser.add_argument("--private-dir", type=Path)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    private_dir = (args.private_dir or manifest_path.parent / "private").resolve()
    try:
        manifest = build_manifest(manifest_path, private_dir, args.update)
        write_manifest(manifest_path, manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Corpus manifest written: {manifest_path} ({len(manifest['documents'])} documents)")
    print("Complete consent, family, field and region labels, obtain second review, then validate it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
