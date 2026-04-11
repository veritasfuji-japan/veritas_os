"""Tests for the file-to-PostgreSQL migration CLI.

Covers the eight required scenarios from the problem statement:
1. Memory import happy path
2. TrustLog import happy path
3. Dry-run mode (memory and trustlog)
4. Duplicate import / re-run safety
5. Malformed source data
6. Partial failure (DB error on individual entries)
7. Post-migration hash-chain verify (mocked PostgreSQL)
8. MigrationReport schema validation

All tests use temporary files and mock PostgreSQL backends — no live
database is required.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from veritas_os.cli.migrate import (
    MigrationReport,
    _migrate_memory,
    _migrate_trustlog,
    _verify_pg_trustlog_chain,
    _format_report,
    main,
)


# ═══════════════════════════════════════════════════════════════════════════
# Shared fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_memory_json(tmp_path: Path) -> Path:
    """Valid memory.json with three records across two users."""
    records = [
        {"user_id": "alice", "key": "k1", "value": {"text": "hello"}, "ts": 1000.0},
        {"user_id": "alice", "key": "k2", "value": {"text": "world"}, "ts": 1001.0},
        {"user_id": "bob", "key": "k1", "value": {"text": "foo"}, "ts": 1002.0},
    ]
    p = tmp_path / "memory.json"
    p.write_text(json.dumps(records), encoding="utf-8")
    return p


@pytest.fixture
def tmp_trustlog_jsonl(tmp_path: Path) -> Path:
    """Valid trust_log.jsonl with two plaintext (unencrypted) entries."""
    entries = [
        {
            "request_id": "req-001",
            "sha256": "a" * 64,
            "sha256_prev": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "decision": "allow",
        },
        {
            "request_id": "req-002",
            "sha256": "b" * 64,
            "sha256_prev": "a" * 64,
            "created_at": "2024-01-01T00:00:01+00:00",
            "decision": "allow",
        },
    ]
    p = tmp_path / "trust_log.jsonl"
    lines = "\n".join(json.dumps(e) for e in entries) + "\n"
    p.write_text(lines, encoding="utf-8")
    return p


def _make_pg_memory_mock(*, inserted: bool = True) -> MagicMock:
    """Return a mock PostgresMemoryStore whose import_record always returns *inserted*."""
    mock = MagicMock()
    mock.import_record = AsyncMock(return_value=inserted)
    return mock


def _make_pg_trustlog_mock(*, inserted: bool = True) -> MagicMock:
    """Return a mock PostgresTrustLogStore whose import_entry always returns success."""

    async def _import_entry(entry: Dict[str, Any], *, dry_run: bool = False):
        rid = str(entry.get("request_id") or entry.get("sha256") or "")
        return rid, inserted

    mock = MagicMock()
    mock.import_entry = _import_entry
    return mock


# ═══════════════════════════════════════════════════════════════════════════
# 1. Memory import — happy path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_memory_happy_path(tmp_memory_json: Path) -> None:
    """All three records in memory.json are migrated successfully."""
    pg_mock = _make_pg_memory_mock(inserted=True)

    with patch("veritas_os.storage.postgresql.PostgresMemoryStore", return_value=pg_mock):
        report = await _migrate_memory(tmp_memory_json, dry_run=False, batch_size=500)

    assert report.migrated == 3
    assert report.duplicates == 0
    assert report.malformed == 0
    assert report.failed == 0
    assert report.dry_run is False
    assert report.success()


# ═══════════════════════════════════════════════════════════════════════════
# 2. TrustLog import — happy path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_happy_path(tmp_trustlog_jsonl: Path) -> None:
    """Both entries in trust_log.jsonl are imported with original hashes preserved."""
    imported_entries: List[Dict[str, Any]] = []

    async def capture_import(entry: Dict[str, Any], *, dry_run: bool = False):
        imported_entries.append(dict(entry))
        return str(entry.get("request_id") or ""), True

    pg_mock = MagicMock()
    pg_mock.import_entry = capture_import

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=False, verify=False, batch_size=500
        )

    assert report.migrated == 2
    assert report.duplicates == 0
    assert report.malformed == 0
    assert report.failed == 0
    assert report.success()

    # Original sha256 / sha256_prev values must be preserved verbatim.
    assert imported_entries[0]["sha256"] == "a" * 64
    assert imported_entries[0]["sha256_prev"] is None
    assert imported_entries[1]["sha256"] == "b" * 64
    assert imported_entries[1]["sha256_prev"] == "a" * 64


# ═══════════════════════════════════════════════════════════════════════════
# 3. Dry-run mode
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_memory_dry_run(tmp_memory_json: Path) -> None:
    """Dry-run reports would-be-migrated count; import_record not called."""
    pg_mock = _make_pg_memory_mock(inserted=True)

    with patch("veritas_os.storage.postgresql.PostgresMemoryStore", return_value=pg_mock):
        report = await _migrate_memory(tmp_memory_json, dry_run=True, batch_size=500)

    assert report.dry_run is True
    assert report.migrated == 3  # "would be inserted"
    assert report.duplicates == 0
    # import_record must receive dry_run=True (no actual DB writes)
    for call in pg_mock.import_record.call_args_list:
        assert call.kwargs.get("dry_run") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_dry_run(tmp_trustlog_jsonl: Path) -> None:
    """Dry-run TrustLog reports entries without writing."""
    received_dry_run_flags: List[bool] = []

    async def check_dry(entry: Dict[str, Any], *, dry_run: bool = False):
        received_dry_run_flags.append(dry_run)
        return str(entry.get("request_id") or ""), True

    pg_mock = MagicMock()
    pg_mock.import_entry = check_dry

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=True, verify=False, batch_size=500
        )

    assert report.dry_run is True
    assert report.migrated == 2
    assert all(flag is True for flag in received_dry_run_flags)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Duplicate import / re-run safety
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_memory_all_duplicates(tmp_memory_json: Path) -> None:
    """Second run: import_record returns False → all counted as duplicates."""
    pg_mock = _make_pg_memory_mock(inserted=False)

    with patch("veritas_os.storage.postgresql.PostgresMemoryStore", return_value=pg_mock):
        report = await _migrate_memory(tmp_memory_json, dry_run=False, batch_size=500)

    assert report.migrated == 0
    assert report.duplicates == 3
    assert report.failed == 0
    # Idempotent re-run is considered successful (no hard failures).
    assert report.success()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_all_duplicates(tmp_trustlog_jsonl: Path) -> None:
    """Second TrustLog run: all entries are duplicates."""
    pg_mock = _make_pg_trustlog_mock(inserted=False)

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=False, verify=False, batch_size=500
        )

    assert report.migrated == 0
    assert report.duplicates == 2
    assert report.success()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_partial_duplicates(tmp_trustlog_jsonl: Path) -> None:
    """First entry is new; second entry is a duplicate (mixed re-run scenario)."""
    call_count = 0

    async def partial_dup(entry: Dict[str, Any], *, dry_run: bool = False):
        nonlocal call_count
        call_count += 1
        rid = str(entry.get("request_id") or "")
        # First call → inserted, subsequent → duplicate
        return rid, call_count == 1

    pg_mock = MagicMock()
    pg_mock.import_entry = partial_dup

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=False, verify=False, batch_size=500
        )

    assert report.migrated == 1
    assert report.duplicates == 1
    assert report.success()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Malformed source data
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_memory_malformed_records(tmp_path: Path) -> None:
    """Malformed memory records are counted, not aborted; valid record succeeds."""
    records = [
        {"user_id": "alice", "value": {"text": "no key field"}},  # missing key
        "not_a_dict",  # invalid type
        None,  # None value
        {"user_id": "alice", "key": "k1", "value": {"text": "valid"}},  # OK
    ]
    p = tmp_path / "bad_memory.json"
    p.write_text(json.dumps(records), encoding="utf-8")

    pg_mock = _make_pg_memory_mock(inserted=True)

    with patch("veritas_os.storage.postgresql.PostgresMemoryStore", return_value=pg_mock):
        report = await _migrate_memory(p, dry_run=False, batch_size=500)

    assert report.malformed == 3  # first 3 records are malformed
    assert report.migrated == 1
    assert len(report.errors) >= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_malformed_jsonl(tmp_path: Path) -> None:
    """Malformed JSONL lines are counted and skipped; valid entries succeed."""
    p = tmp_path / "mixed.jsonl"
    valid_entry = {
        "request_id": "req-valid",
        "sha256": "c" * 64,
        "sha256_prev": None,
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    lines = (
        "{not valid json}\n"
        "42\n"  # not a dict
        + json.dumps(valid_entry)
        + "\n"
        + '{"sha256_prev": null}\n'  # missing request_id and sha256
    )
    p.write_text(lines, encoding="utf-8")

    pg_mock = _make_pg_trustlog_mock(inserted=True)

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(p, dry_run=False, verify=False, batch_size=500)

    assert report.malformed == 3  # invalid json, non-dict, missing id
    assert report.migrated == 1
    assert len(report.errors) >= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_memory_source_not_found(tmp_path: Path) -> None:
    """Missing source file → report has failed=1, no crash."""
    missing = tmp_path / "nonexistent.json"
    report = await _migrate_memory(missing, dry_run=False, batch_size=500)

    assert report.failed >= 1
    assert not report.success()
    assert any("source not found" in e for e in report.errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_source_not_found(tmp_path: Path) -> None:
    """Missing source file → report has failed=1, no crash."""
    missing = tmp_path / "nonexistent.jsonl"
    report = await _migrate_trustlog(
        missing, dry_run=False, verify=False, batch_size=500
    )

    assert report.failed >= 1
    assert not report.success()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Partial failure
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_memory_partial_db_failure(tmp_memory_json: Path) -> None:
    """DB error on second record → failed=1, migration continues for remaining."""
    call_count = 0

    async def side_effect(key: str, value: Any, *, user_id: str, dry_run: bool = False):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated DB failure")
        return True

    pg_mock = MagicMock()
    pg_mock.import_record = side_effect

    with patch("veritas_os.storage.postgresql.PostgresMemoryStore", return_value=pg_mock):
        report = await _migrate_memory(tmp_memory_json, dry_run=False, batch_size=500)

    assert report.migrated == 2
    assert report.failed == 1
    assert not report.success()
    assert len(report.errors) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_partial_db_failure(tmp_trustlog_jsonl: Path) -> None:
    """DB error on first entry → failed=1, second entry succeeds."""
    call_count = 0

    async def side_effect(entry: Dict[str, Any], *, dry_run: bool = False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated DB failure")
        return str(entry.get("request_id") or ""), True

    pg_mock = MagicMock()
    pg_mock.import_entry = side_effect

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=False, verify=False, batch_size=500
        )

    assert report.failed == 1
    assert report.migrated == 1
    assert not report.success()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Post-migration hash-chain verify
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_verify_pass(tmp_trustlog_jsonl: Path) -> None:
    """--verify produces verify_ok=True when chain is intact."""
    pg_mock = _make_pg_trustlog_mock(inserted=True)

    # Build a mock iter_entries that yields entries in chain order.
    chain_entries = [
        {"request_id": "req-001", "sha256": "a" * 64, "sha256_prev": None},
        {"request_id": "req-002", "sha256": "b" * 64, "sha256_prev": "a" * 64},
    ]

    async def mock_iter(limit: int = 100, offset: int = 0) -> AsyncIterator[Dict[str, Any]]:
        for e in chain_entries[offset : offset + limit]:
            yield e

    pg_mock.iter_entries = mock_iter

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=False, verify=True, batch_size=500
        )

    assert report.migrated == 2
    assert report.verify_ok is True
    assert report.verify_detail is not None
    assert report.verify_detail.get("ok") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_verify_fail(tmp_trustlog_jsonl: Path) -> None:
    """--verify produces verify_ok=False when chain is broken."""
    pg_mock = _make_pg_trustlog_mock(inserted=True)

    broken_entries = [
        {"request_id": "req-001", "sha256": "a" * 64, "sha256_prev": None},
        {
            "request_id": "req-002",
            "sha256": "b" * 64,
            "sha256_prev": "WRONG" + "0" * 59,  # broken prev_hash
        },
    ]

    async def mock_iter(limit: int = 100, offset: int = 0) -> AsyncIterator[Dict[str, Any]]:
        for e in broken_entries[offset : offset + limit]:
            yield e

    pg_mock.iter_entries = mock_iter

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=False, verify=True, batch_size=500
        )

    assert report.verify_ok is False
    assert report.verify_detail is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_migrate_trustlog_verify_skipped_on_dry_run(tmp_trustlog_jsonl: Path) -> None:
    """--verify is silently skipped during dry-run (no data to verify)."""
    pg_mock = _make_pg_trustlog_mock(inserted=True)

    with patch("veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock):
        report = await _migrate_trustlog(
            tmp_trustlog_jsonl, dry_run=True, verify=True, batch_size=500
        )

    # verify should not run for dry-run
    assert report.verify_ok is None
    assert report.dry_run is True


# ═══════════════════════════════════════════════════════════════════════════
# 8. MigrationReport schema
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_migration_report_schema() -> None:
    """MigrationReport contains all required fields with correct types."""
    report = MigrationReport(
        source="/data/trust_log.jsonl",
        migrated=5,
        skipped=0,
        duplicates=2,
        malformed=1,
        failed=0,
        dry_run=False,
        verify_ok=True,
        verify_detail={"ok": True, "total_entries": 5},
        errors=["line[0] json_error: ..."],
    )

    d = asdict(report)

    required_keys = {
        "source",
        "migrated",
        "skipped",
        "duplicates",
        "malformed",
        "failed",
        "dry_run",
        "verify_ok",
        "verify_detail",
        "errors",
    }
    assert required_keys.issubset(d.keys())

    assert isinstance(d["migrated"], int)
    assert isinstance(d["skipped"], int)
    assert isinstance(d["duplicates"], int)
    assert isinstance(d["malformed"], int)
    assert isinstance(d["failed"], int)
    assert isinstance(d["dry_run"], bool)
    assert isinstance(d["errors"], list)

    # Computed helpers
    assert report.total_processed() == 8  # 5+0+2+1+0
    # success() requires both failed==0 AND malformed==0
    assert report.success() is False  # malformed=1 → not a clean run


@pytest.mark.unit
def test_migration_report_success_only_when_clean() -> None:
    """success() returns False when malformed > 0 or failed > 0."""
    r1 = MigrationReport(migrated=10, failed=0, malformed=0)
    assert r1.success() is True

    r2 = MigrationReport(migrated=9, failed=1, malformed=0)
    assert r2.success() is False

    r3 = MigrationReport(migrated=9, failed=0, malformed=1)
    assert r3.success() is False


# ═══════════════════════════════════════════════════════════════════════════
# Report formatting
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_format_report_text() -> None:
    """Text report contains key section headers and counts."""
    report = MigrationReport(
        source="/logs/memory.json",
        migrated=10,
        duplicates=2,
        dry_run=True,
    )
    text = _format_report(report, output_json=False)

    assert "Migration Report" in text
    assert "Migrated:" in text
    assert "Duplicates:" in text
    assert "Dry-run:" in text
    assert "10" in text


@pytest.mark.unit
def test_format_report_json_parseable() -> None:
    """JSON report is valid JSON with all required fields."""
    report = MigrationReport(source="/logs/tl.jsonl", migrated=5, verify_ok=True)
    raw = _format_report(report, output_json=True)
    parsed = json.loads(raw)

    assert parsed["migrated"] == 5
    assert parsed["verify_ok"] is True
    assert "source" in parsed


# ═══════════════════════════════════════════════════════════════════════════
# CLI main() entry point (argument parsing + exit codes)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_main_memory_dry_run_exit_zero(tmp_memory_json: Path, capsys) -> None:
    """CLI returns exit code 0 for successful dry-run."""
    pg_mock = _make_pg_memory_mock(inserted=True)

    with patch("veritas_os.storage.postgresql.PostgresMemoryStore", return_value=pg_mock):
        code = main(["memory", "--source", str(tmp_memory_json), "--dry-run"])

    assert code == 0
    captured = capsys.readouterr()
    assert "Migrated:" in captured.out


@pytest.mark.unit
def test_main_trustlog_dry_run_json_output(tmp_trustlog_jsonl: Path, capsys) -> None:
    """CLI --json flag produces JSON output on stdout."""
    pg_mock = _make_pg_trustlog_mock(inserted=True)

    with patch(
        "veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock
    ):
        code = main(
            ["trustlog", "--source", str(tmp_trustlog_jsonl), "--dry-run", "--json"]
        )

    assert code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["dry_run"] is True
    assert "migrated" in parsed


@pytest.mark.unit
def test_main_exit_one_on_failure(tmp_path: Path, capsys) -> None:
    """CLI returns exit code 1 when failures are present."""
    # Use a non-existent source file — causes failed=1
    missing = tmp_path / "no.json"
    code = main(["memory", "--source", str(missing)])
    assert code == 1


@pytest.mark.unit
def test_main_exit_two_on_fatal(tmp_path: Path, capsys) -> None:
    """CLI returns exit code 2 on unexpected exception."""
    p = tmp_path / "memory.json"
    p.write_text(json.dumps([{"user_id": "u", "key": "k", "value": {}}]))

    with patch(
        "veritas_os.cli.migrate._migrate_memory",
        side_effect=RuntimeError("kaboom"),
    ):
        code = main(["memory", "--source", str(p)])

    assert code == 2


# ═══════════════════════════════════════════════════════════════════════════
# PostgreSQL chain verifier unit tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_pg_chain_empty_db() -> None:
    """Empty trustlog_entries table → ok=True, total=0."""

    async def empty_iter(limit: int = 100, offset: int = 0) -> AsyncIterator[Dict]:
        return
        yield  # make it a generator

    pg_mock = MagicMock()
    pg_mock.iter_entries = empty_iter

    with patch(
        "veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock
    ):
        result = await _verify_pg_trustlog_chain()

    assert result["ok"] is True
    assert result["total_entries"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_pg_chain_intact() -> None:
    """Intact two-entry chain → ok=True."""
    chain = [
        {"request_id": "r1", "sha256": "a" * 64, "sha256_prev": None},
        {"request_id": "r2", "sha256": "b" * 64, "sha256_prev": "a" * 64},
    ]

    async def mock_iter(limit: int = 100, offset: int = 0) -> AsyncIterator[Dict]:
        for e in chain[offset : offset + limit]:
            yield e

    pg_mock = MagicMock()
    pg_mock.iter_entries = mock_iter

    with patch(
        "veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock
    ):
        result = await _verify_pg_trustlog_chain()

    assert result["ok"] is True
    assert result["total_entries"] == 2
    assert result["invalid_entries"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_pg_chain_broken() -> None:
    """Broken chain (wrong sha256_prev) → ok=False, invalid_entries=1."""
    chain = [
        {"request_id": "r1", "sha256": "a" * 64, "sha256_prev": None},
        # sha256_prev does NOT match previous sha256
        {"request_id": "r2", "sha256": "b" * 64, "sha256_prev": "x" * 64},
    ]

    async def mock_iter(limit: int = 100, offset: int = 0) -> AsyncIterator[Dict]:
        for e in chain[offset : offset + limit]:
            yield e

    pg_mock = MagicMock()
    pg_mock.iter_entries = mock_iter

    with patch(
        "veritas_os.storage.postgresql.PostgresTrustLogStore", return_value=pg_mock
    ):
        result = await _verify_pg_trustlog_chain()

    assert result["ok"] is False
    assert result["invalid_entries"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "sha256_prev_mismatch"
