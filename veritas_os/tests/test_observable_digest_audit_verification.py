"""Tests for read-only observable-digest audit reconstruction/verification."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from veritas_os.audit.observable_digest_audit_emission import (
    ObservableDigestAuditEmissionError,
    append_observable_digest_audit_entry,
)
from veritas_os.audit.observable_digest_audit_entry import (
    build_observable_digest_failure_audit_entry,
)
from veritas_os.audit.observable_digest_audit_verification import (
    EVIDENCE_NOT_ESTABLISHED,
    EVIDENCE_RECEIPT_CONFIRMED,
    LINE_MALFORMED_JSON,
    LINE_RECONSTRUCTED,
    LOCAL_DURABILITY_RECEIPT_CONFIRMED,
    RECEIPT_MATCHED,
    RECEIPT_UNMATCHED,
    SOURCE_MISSING,
    SOURCE_PRESENT,
    SOURCE_REJECTED_SYMLINK,
    reconstruct_and_verify_observable_digest_audit,
    uncertainty_from_emission_error,
)
from veritas_os.audit.observable_digest_failure_codes import (
    ObservableDigestFailurePredicate,
)


def _entry(
    *,
    event_id: str = "evt-001",
    timestamp: str = "2026-09-22T00:00:00Z",
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
    )


def _canonical_line(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def test_reconstructs_emitted_record_and_matches_success_receipt(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    receipt = append_observable_digest_audit_entry(entry, path=target)

    report = reconstruct_and_verify_observable_digest_audit(
        path=target,
        receipts=[receipt],
    )

    assert report.source_status == SOURCE_PRESENT
    assert report.source_order_preserved is True
    assert report.physical_line_count == 1
    assert report.reconstructed_count == 1
    assert report.malformed_count == 0
    assert report.absence_proven is False

    line = report.lines[0]
    assert line.status == LINE_RECONSTRUCTED
    assert line.independently_reconstructable is True
    assert line.canonical_encoding_matches is True
    assert line.payload() == entry.to_contract_dict()
    assert line.emission_status == EVIDENCE_RECEIPT_CONFIRMED
    assert line.durability_status == LOCAL_DURABILITY_RECEIPT_CONFIRMED
    assert line.matched_receipt_index == 0

    assert report.receipts[0].status == RECEIPT_MATCHED
    assert report.receipts[0].matched_line_number == 1


def test_source_presence_without_receipt_does_not_invent_emission_or_durability(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    target.write_bytes(_canonical_line(entry.to_contract_dict()))

    report = reconstruct_and_verify_observable_digest_audit(path=target)

    line = report.lines[0]
    assert line.independently_reconstructable is True
    assert line.emission_status == EVIDENCE_NOT_ESTABLISHED
    assert line.durability_status == EVIDENCE_NOT_ESTABLISHED
    assert line.matched_receipt_index is None


def test_repeated_records_remain_visible_one_for_one(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    first_receipt = append_observable_digest_audit_entry(entry, path=target)
    second_receipt = append_observable_digest_audit_entry(entry, path=target)

    report = reconstruct_and_verify_observable_digest_audit(
        path=target,
        receipts=[first_receipt, second_receipt],
    )

    assert report.physical_line_count == 2
    assert report.reconstructed_count == 2
    assert [line.line_number for line in report.lines] == [1, 2]
    assert [line.event_id for line in report.lines] == ["evt-001", "evt-001"]
    assert report.lines[0].raw_sha256 == report.lines[1].raw_sha256
    assert report.lines[0].matched_receipt_index == 0
    assert report.lines[1].matched_receipt_index == 1


def test_one_receipt_cannot_prove_two_identical_records(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    receipt = append_observable_digest_audit_entry(entry, path=target)
    append_observable_digest_audit_entry(entry, path=target)

    report = reconstruct_and_verify_observable_digest_audit(
        path=target,
        receipts=[receipt],
    )

    assert report.lines[0].durability_status == (
        LOCAL_DURABILITY_RECEIPT_CONFIRMED
    )
    assert report.lines[1].durability_status == EVIDENCE_NOT_ESTABLISHED
    assert report.lines[1].matched_receipt_index is None


def test_physical_source_order_is_preserved_without_timestamp_interpretation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    later_timestamp = _entry(
        event_id="evt-first",
        timestamp="2026-09-22T00:00:10Z",
    )
    earlier_timestamp = _entry(
        event_id="evt-second",
        timestamp="2026-09-22T00:00:01Z",
    )
    append_observable_digest_audit_entry(later_timestamp, path=target)
    append_observable_digest_audit_entry(earlier_timestamp, path=target)

    report = reconstruct_and_verify_observable_digest_audit(path=target)

    assert report.source_order_preserved is True
    assert [line.event_id for line in report.lines] == [
        "evt-first",
        "evt-second",
    ]


def test_malformed_line_remains_visible_and_later_record_is_still_reconstructed(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry(event_id="evt-valid")
    target.write_bytes(b"{not-json}\n" + _canonical_line(entry.to_contract_dict()))

    report = reconstruct_and_verify_observable_digest_audit(path=target)

    assert report.physical_line_count == 2
    assert report.lines[0].status == LINE_MALFORMED_JSON
    assert report.lines[0].independently_reconstructable is False
    assert report.lines[1].status == LINE_RECONSTRUCTED
    assert report.lines[1].event_id == "evt-valid"
    assert report.malformed_count == 1


def test_receipt_hash_mismatch_does_not_upgrade_record_to_confirmed(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    receipt = append_observable_digest_audit_entry(entry, path=target)

    payload = entry.to_contract_dict()
    payload["actor"] = "modified-after-emission"
    target.write_bytes(_canonical_line(payload))

    report = reconstruct_and_verify_observable_digest_audit(
        path=target,
        receipts=[receipt],
    )

    assert report.lines[0].status == LINE_RECONSTRUCTED
    assert report.lines[0].emission_status == EVIDENCE_NOT_ESTABLISHED
    assert report.lines[0].durability_status == EVIDENCE_NOT_ESTABLISHED
    assert report.receipts[0].status == RECEIPT_UNMATCHED
    assert report.receipts[0].reason == "record_hash_mismatch"


def test_noncanonical_rewrite_does_not_match_original_receipt(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    receipt = append_observable_digest_audit_entry(entry, path=target)

    target.write_text(
        json.dumps(entry.to_contract_dict(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = reconstruct_and_verify_observable_digest_audit(
        path=target,
        receipts=[receipt],
    )

    assert report.lines[0].independently_reconstructable is True
    assert report.lines[0].canonical_encoding_matches is False
    assert report.lines[0].emission_status == EVIDENCE_NOT_ESTABLISHED
    assert report.receipts[0].status == RECEIPT_UNMATCHED


def test_unsupported_schema_remains_visible_without_current_schema_claim(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    payload = _entry().to_contract_dict()
    payload["v1_schema_version"] = "9.9"
    target.write_bytes(_canonical_line(payload))

    report = reconstruct_and_verify_observable_digest_audit(path=target)

    line = report.lines[0]
    assert line.status == LINE_RECONSTRUCTED
    assert line.schema_version == "9.9"
    assert line.schema_supported is False
    assert line.payload() == payload


def test_missing_source_does_not_claim_historical_absence(tmp_path: Path) -> None:
    target = tmp_path / "missing.jsonl"

    report = reconstruct_and_verify_observable_digest_audit(path=target)

    assert report.source_status == SOURCE_MISSING
    assert report.absence_proven is False
    assert report.lines == ()
    assert report.source_order_preserved is False


def test_uncertainty_is_preserved_even_when_related_record_is_later_visible(
    tmp_path: Path,
) -> None:
    target = tmp_path / "audit.jsonl"
    entry = _entry()
    receipt = append_observable_digest_audit_entry(entry, path=target)
    error = ObservableDigestAuditEmissionError(
        stage="fsync",
        outcome="DURABILITY_UNKNOWN",
        path=target,
        record_sha256=receipt.record_sha256,
        bytes_written=receipt.bytes_written,
        detail="OSError",
    )
    uncertainty = uncertainty_from_emission_error(error)

    report = reconstruct_and_verify_observable_digest_audit(
        path=target,
        receipts=[receipt],
        uncertainties=[uncertainty],
    )

    assert report.lines[0].durability_status == (
        LOCAL_DURABILITY_RECEIPT_CONFIRMED
    )
    assert report.uncertainties == (uncertainty,)
    assert report.uncertainties[0].outcome == "DURABILITY_UNKNOWN"


def test_verification_is_read_only(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    append_observable_digest_audit_entry(_entry(), path=target)
    before = target.read_bytes()

    reconstruct_and_verify_observable_digest_audit(path=target)

    assert target.read_bytes() == before


def test_symbolic_link_source_is_rejected_without_following_it(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real.jsonl"
    real.write_bytes(_canonical_line(_entry().to_contract_dict()))
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links unavailable on this platform")

    report = reconstruct_and_verify_observable_digest_audit(path=link)

    assert report.source_status == SOURCE_REJECTED_SYMLINK
    assert report.lines == ()
    assert report.absence_proven is False


def test_report_and_lines_are_immutable(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    target.write_bytes(_canonical_line(_entry().to_contract_dict()))
    report = reconstruct_and_verify_observable_digest_audit(path=target)

    with pytest.raises(FrozenInstanceError):
        report.physical_line_count = 0

    with pytest.raises(FrozenInstanceError):
        report.lines[0].status = "CHANGED"


def test_requires_explicit_supported_input_types(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="pathlib.Path"):
        reconstruct_and_verify_observable_digest_audit(
            path=str(tmp_path / "audit.jsonl"),  # type: ignore[arg-type]
        )

    target = tmp_path / "audit.jsonl"
    target.write_bytes(_canonical_line(_entry().to_contract_dict()))

    with pytest.raises(TypeError, match="EmissionReceipt"):
        reconstruct_and_verify_observable_digest_audit(
            path=target,
            receipts=[{"event_id": "evt"}],  # type: ignore[list-item]
        )

    with pytest.raises(TypeError, match="Uncertainty"):
        reconstruct_and_verify_observable_digest_audit(
            path=target,
            uncertainties=[{"outcome": "unknown"}],  # type: ignore[list-item]
        )
