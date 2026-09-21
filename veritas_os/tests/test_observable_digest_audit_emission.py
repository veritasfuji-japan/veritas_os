"""Tests for append-only observable-digest audit emission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from veritas_os.audit.observable_digest_audit_emission import (
    ObservableDigestAuditEmissionError,
    append_observable_digest_audit_entry,
)
from veritas_os.audit.observable_digest_audit_entry import (
    ObservableDigestAuditExecutionObservation,
    build_observable_digest_failure_audit_entry,
)
from veritas_os.audit.observable_digest_failure_codes import (
    ObservableDigestFailurePredicate,
)


def _entry(
    *,
    event_id: str = "evt-001",
    timestamp: str = "2026-09-21T14:00:00Z",
    execution: ObservableDigestAuditExecutionObservation | None = None,
):
    return build_observable_digest_failure_audit_entry(
        event_id=event_id,
        timestamp=timestamp,
        predicates=[ObservableDigestFailurePredicate.DIGEST_MISMATCH],
        validation_result="failed",
        actor="wat_boundary",
        locator="store://tenant-x/observable/abc",
        resolved_digest="sha256:resolved",
        expected_digest="sha256:expected",
        caller_id_hash="sha256:caller",
        execution=execution,
    )


def _lines(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_emits_exact_contract_payload_and_returns_fsynced_receipt(
    tmp_path: Path,
) -> None:
    entry = _entry()
    target = tmp_path / "audit.jsonl"

    receipt = append_observable_digest_audit_entry(entry, path=target)

    assert _lines(target) == [entry.to_contract_dict()]
    assert receipt.event_id == entry.event_id
    assert receipt.schema_version == entry.v1_schema_version
    assert receipt.path == str(target)
    assert receipt.durability == "fsync_completed"

    raw_line = target.read_bytes().rstrip(b"\n")
    assert receipt.record_sha256 == hashlib.sha256(raw_line).hexdigest()
    assert receipt.bytes_written == len(raw_line) + 1


def test_emission_preserves_call_order(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    first = _entry(event_id="evt-001", timestamp="2026-09-21T14:00:00Z")
    second = _entry(event_id="evt-002", timestamp="2026-09-21T14:00:01Z")

    append_observable_digest_audit_entry(first, path=target)
    append_observable_digest_audit_entry(second, path=target)

    records = _lines(target)
    assert [record["event_id"] for record in records] == ["evt-001", "evt-002"]


def test_emitter_does_not_deduplicate_or_interpret_repeated_events(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()

    append_observable_digest_audit_entry(entry, path=target)
    append_observable_digest_audit_entry(entry, path=target)

    assert _lines(target) == [entry.to_contract_dict(), entry.to_contract_dict()]


def test_emitter_does_not_create_execution_evidence(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()

    append_observable_digest_audit_entry(entry, path=target)

    record = _lines(target)[0]
    assert record["execution_observed"] is False
    assert "action_taken" not in record
    assert "remediation_attempts" not in record


def test_explicit_execution_fact_is_recorded_without_new_interpretation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry(
        execution=ObservableDigestAuditExecutionObservation(
            action_taken="blocked_pending_review",
            remediation_attempts=1,
        )
    )

    append_observable_digest_audit_entry(entry, path=target)

    assert _lines(target) == [entry.to_contract_dict()]


def test_parent_directory_must_exist_and_is_not_created(tmp_path: Path) -> None:
    missing_parent = tmp_path / "missing"
    target = missing_parent / "audit.jsonl"

    with pytest.raises(ValueError, match="parent directory must already exist"):
        append_observable_digest_audit_entry(_entry(), path=target)

    assert not missing_parent.exists()


def test_directory_target_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be a directory"):
        append_observable_digest_audit_entry(_entry(), path=tmp_path)


def test_symbolic_link_target_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.jsonl"
    real.write_text("", encoding="utf-8")
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links unavailable on this platform")

    with pytest.raises(ValueError, match="symbolic link"):
        append_observable_digest_audit_entry(_entry(), path=link)


def test_open_failure_is_explicit_and_not_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "audit.jsonl"

    def fail_open(*args: object, **kwargs: object) -> int:
        raise PermissionError("denied")

    monkeypatch.setattr(
        "veritas_os.audit.observable_digest_audit_emission.os.open",
        fail_open,
    )

    with pytest.raises(ObservableDigestAuditEmissionError) as captured:
        append_observable_digest_audit_entry(_entry(), path=target)

    assert captured.value.stage == "open"
    assert captured.value.outcome == "NOT_EMITTED"
    assert captured.value.bytes_written is None


def test_short_write_is_explicit_emission_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "audit.jsonl"

    def short_write(fd: int, data: bytes) -> int:
        return 1

    monkeypatch.setattr(
        "veritas_os.audit.observable_digest_audit_emission.os.write",
        short_write,
    )

    with pytest.raises(ObservableDigestAuditEmissionError) as captured:
        append_observable_digest_audit_entry(_entry(), path=target)

    assert captured.value.stage == "write"
    assert captured.value.outcome == "EMISSION_UNKNOWN"
    assert captured.value.bytes_written == 1


def test_fsync_failure_is_explicit_durability_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "audit.jsonl"

    def fail_fsync(fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(
        "veritas_os.audit.observable_digest_audit_emission.os.fsync",
        fail_fsync,
    )

    with pytest.raises(ObservableDigestAuditEmissionError) as captured:
        append_observable_digest_audit_entry(_entry(), path=target)

    assert captured.value.stage == "fsync"
    assert captured.value.outcome == "DURABILITY_UNKNOWN"
    assert captured.value.bytes_written is not None
    assert len(_lines(target)) == 1


def test_receipt_is_immutable(tmp_path: Path) -> None:
    receipt = append_observable_digest_audit_entry(
        _entry(), path=tmp_path / "audit.jsonl"
    )

    with pytest.raises(FrozenInstanceError):
        receipt.bytes_written = 0


def test_requires_explicit_supported_types(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="ObservableDigestFailureAuditEntry"):
        append_observable_digest_audit_entry(
            {"event_id": "evt-001"},  # type: ignore[arg-type]
            path=tmp_path / "audit.jsonl",
        )

    with pytest.raises(TypeError, match="pathlib.Path"):
        append_observable_digest_audit_entry(
            _entry(),
            path=str(tmp_path / "audit.jsonl"),  # type: ignore[arg-type]
        )
