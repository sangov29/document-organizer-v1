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


def database_fingerprint(name):
    """Compare logical rows as multisets and include sequence state.

    Text pg_dump output is unsuitable for this comparison: header content and
    row traversal order are not part of the database's logical state.
    """
    def query(sql):
        return postgres("psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                        "-U", DB_USER, "-d", name, "-c", sql).decode().strip()

    tables = query("SELECT quote_ident(schemaname)||'.'||quote_ident(tablename) "
                   "FROM pg_tables WHERE schemaname='public' ORDER BY schemaname,tablename").splitlines()
    sequences = query("SELECT quote_ident(sequence_schema)||'.'||quote_ident(sequence_name) "
                      "FROM information_schema.sequences WHERE sequence_schema='public' "
                      "ORDER BY sequence_schema,sequence_name").splitlines()
    result = {"tables": {}, "sequences": {}}
    for table in tables:
        # Repeated equal rows remain significant because they contribute to
        # both count and ordered aggregate; physical row order does not.
        result["tables"][table] = query(
            "SELECT count(*)||':'||md5(COALESCE(string_agg(row_hash,',' ORDER BY row_hash),'')) "
            f"FROM (SELECT md5(to_jsonb(t)::text) AS row_hash FROM {table} AS t) AS rows"
        )
    for sequence in sequences:
        result["sequences"][sequence] = query(f"SELECT last_value||':'||is_called FROM {sequence}")
    return result


def database_roundtrip():
    name = "restore_probe_" + uuid.uuid4().hex[:16]
    verification_name = name + "_verify"
    with tempfile.TemporaryDirectory(prefix="acceptance-restore-") as private_dir:
        os.chmod(private_dir, 0o700)
        dump_path = Path(private_dir) / "database.dump"
        dump_path.write_bytes(postgres("pg_dump", "-Fc", "-U", DB_USER, "-d", DB_NAME))
        try:
            postgres("createdb", "-U", DB_USER, name)
            postgres("pg_restore", "--no-owner", "--no-privileges", "-U", DB_USER, "-d", name,
                     input_bytes=dump_path.read_bytes())
            restored = database_fingerprint(name)
            # The live source can change while workers process documents. Verify
            # that the same immutable dump restores identically twice instead.
            postgres("createdb", "-U", DB_USER, verification_name)
            postgres("pg_restore", "--no-owner", "--no-privileges", "-U", DB_USER, "-d", verification_name,
                     input_bytes=dump_path.read_bytes())
            if restored != database_fingerprint(verification_name):
                raise RuntimeError("restored PostgreSQL rows or sequences differ between isolated restores")
            return {"dump_sha256": hashlib.sha256(dump_path.read_bytes()).hexdigest(),
                    "data_sha256": hashlib.sha256(json.dumps(restored, sort_keys=True).encode()).hexdigest(),
                    "table_count": len(restored["tables"])}
        finally:
            postgres("dropdb", "-U", DB_USER, "--if-exists", "--force", verification_name)
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
