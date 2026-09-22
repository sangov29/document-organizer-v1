"""Prove a disposable PostgreSQL and object-store restore after acceptance.

Run from the repository root on the acceptance Docker stack. This probe never
restores into the application database or bucket and emits only counts/digests.
Temporary plaintext snapshots are removed when the probe exits. It is not a
production backup policy, retention schedule, or recovery-time benchmark.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "acceptance/docker-compose.acceptance.yml"]
DB_USER = "docorganizer"
DB_NAME = "docorganizer"


def docker(*args, input_bytes=None):
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", *args], cwd=ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        # Database and object-store error text can contain sensitive content.
        raise RuntimeError(f"container command failed ({args[0]}, exit {result.returncode})")
    return result.stdout


def postgres(*args, input_bytes=None):
    return docker("postgres", *args, input_bytes=input_bytes)


def database_roundtrip():
    name = "restore_probe_" + uuid.uuid4().hex[:16]
    source = postgres("pg_dump", "-U", DB_USER, "-d", DB_NAME, "--data-only", "--column-inserts")
    with tempfile.TemporaryDirectory(prefix="acceptance-restore-") as private_dir:
        os.chmod(private_dir, 0o700)
        dump_path = Path(private_dir) / "database.dump"
        dump_path.write_bytes(postgres("pg_dump", "-Fc", "-U", DB_USER, "-d", DB_NAME))
        try:
            postgres("createdb", "-U", DB_USER, name)
            postgres("pg_restore", "--no-owner", "--no-privileges", "-U", DB_USER, "-d", name,
                     input_bytes=dump_path.read_bytes())
            restored = postgres("pg_dump", "-U", DB_USER, "-d", name, "--data-only", "--column-inserts")
            if source != restored:
                raise RuntimeError("restored PostgreSQL rows or sequences differ from source")
            return {"dump_sha256": hashlib.sha256(dump_path.read_bytes()).hexdigest(),
                    "data_sha256": hashlib.sha256(restored).hexdigest()}
        finally:
            postgres("dropdb", "-U", DB_USER, "--if-exists", "--force", name)


def object_roundtrip():
    # The backend image already contains boto3 and the acceptance S3 settings.
    # The child only writes a redacted JSON summary, never object bytes.
    result = docker("backend", "python", "/acceptance/tools/backup_restore_probe.py", "--objects")
    return json.loads(result)


def probe_objects():
    from app.services.storage import storage

    client, source_bucket = storage.client, storage.bucket
    restored_bucket = "restore-probe-" + uuid.uuid4().hex[:20]
    count = 0
    checksum = hashlib.sha256()
    with tempfile.TemporaryFile() as snapshot:
        with tarfile.open(fileobj=snapshot, mode="w") as archive:
            pager = client.get_paginator("list_objects_v2")
            for page in pager.paginate(Bucket=source_bucket):
                for entry in page.get("Contents", []):
                    key = entry["Key"]
                    response = client.get_object(Bucket=source_bucket, Key=key)
                    data = response["Body"].read()
                    payload = json.dumps({"key": key, "content_type": response.get("ContentType")},
                                         separators=(",", ":")).encode() + b"\n" + data
                    member = tarfile.TarInfo(name=f"object-{count:08d}")
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
                    checksum.update(key.encode() + b"\0" + hashlib.sha256(data).digest())
                    count += 1
        if count == 0:
            raise RuntimeError("no document objects available for the restore probe")
        client.create_bucket(Bucket=restored_bucket)
        try:
            restored_count = 0
            restored_hash = hashlib.sha256()
            snapshot.seek(0)
            with tarfile.open(fileobj=snapshot, mode="r") as archive:
                for member in archive:
                    stream = archive.extractfile(member)
                    if not stream:
                        raise RuntimeError("snapshot contains a non-file member")
                    metadata, data = stream.read().split(b"\n", 1)
                    fields = json.loads(metadata)
                    client.put_object(Bucket=restored_bucket, Key=fields["key"], Body=data,
                                      ContentType=fields["content_type"] or "application/octet-stream")
                    actual = client.get_object(Bucket=restored_bucket, Key=fields["key"])["Body"].read()
                    restored_hash.update(fields["key"].encode() + b"\0" + hashlib.sha256(actual).digest())
                    restored_count += 1
            if restored_count != count or restored_hash.digest() != checksum.digest():
                raise RuntimeError("restored object content differs from snapshot")
            return {"object_count": count, "restored_count": restored_count,
                    "content_sha256": restored_hash.hexdigest()}
        finally:
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=restored_bucket):
                for entry in page.get("Contents", []):
                    client.delete_object(Bucket=restored_bucket, Key=entry["Key"])
            client.delete_bucket(Bucket=restored_bucket)


if __name__ == "__main__":
    if sys.argv[1:] == ["--objects"]:
        print(json.dumps(probe_objects(), sort_keys=True))
    elif len(sys.argv) == 2:
        output = Path(sys.argv[1])
        result = {"database": database_roundtrip(), "objects": object_roundtrip(),
                  "restored_to_isolated_targets": True}
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("Isolated database and object restore verified")
    else:
        raise SystemExit("usage: backup_restore_probe.py EVIDENCE_JSON")
