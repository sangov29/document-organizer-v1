"""Keep the operational probe isolated and prevent false restore evidence."""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "backup_restore_probe", ROOT / "acceptance" / "tools" / "backup_restore_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_database_mismatch_fails_and_disposable_database_is_dropped(monkeypatch):
    calls = []

    def fake_postgres(*args, input_bytes=None):
        calls.append(args)
        if args[0] == "pg_dump":
            return b"binary snapshot"
        return b""

    monkeypatch.setattr(probe, "postgres", fake_postgres)
    monkeypatch.setattr(probe, "database_fingerprint", lambda name: {
        "tables": {"public.documents": "2:aaa" if name == "docorganizer" else "1:bbb"},
        "sequences": {},
    })
    with pytest.raises(RuntimeError, match="restored PostgreSQL rows"):
        probe.database_roundtrip()
    created = next(c for c in calls if c[0] == "createdb")[-1]
    assert created.startswith("restore_probe_")
    assert next(c for c in calls if c[0] == "dropdb")[-1] == created
    assert all(c[-1] != "docorganizer" for c in calls if c[0] in {"createdb", "dropdb"})


def test_fingerprint_uses_row_multiset_and_checks_sequence_state(monkeypatch):
    commands = []

    def fake_postgres(*args, input_bytes=None):
        sql = args[-1]
        commands.append(sql)
        if "FROM pg_tables" in sql:
            return b"public.documents\n"
        if "FROM information_schema.sequences" in sql:
            return b"public.document_counter\n"
        if "FROM public.documents AS t" in sql:
            return b"2:aaa\n"
        if "FROM public.document_counter" in sql:
            return b"3:true\n"
        raise AssertionError("unexpected query")

    monkeypatch.setattr(probe, "postgres", fake_postgres)
    assert probe.database_fingerprint("docorganizer") == {
        "tables": {"public.documents": "2:aaa"},
        "sequences": {"public.document_counter": "3:true"},
    }
    assert any("ORDER BY row_hash" in sql for sql in commands)


def test_restore_probe_is_mandatory_and_excludes_snapshot_bytes_from_evidence():
    runner = (ROOT / "acceptance" / "run-local.sh").read_text()
    assert 'BACKUP_RESTORE_EXIT=${PIPESTATUS[0]}' in runner
    assert '$BACKUP_RESTORE_EXIT -ne 0' in runner
    assert '"backup_restore_json": "backup-restore.json"' in runner
    source = (ROOT / "acceptance" / "tools" / "backup_restore_probe.py").read_text()
    assert 'TemporaryDirectory(prefix="acceptance-restore-")' in source
    assert 'TemporaryFile()' in source
    assert 'dropdb' in source and 'delete_bucket' in source
