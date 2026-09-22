"""Read-only reconstruction and verification for observable-digest audit JSONL.

This layer increases observability without increasing authority. It reads an
existing audit JSONL source and reports only what the supplied evidence can
establish.

The verifier deliberately distinguishes:

    current source reconstruction
    != successful emission evidence
    != successful local durability evidence

A record that can be parsed from the source is independently reconstructable
at verification time. That fact alone does not prove that the append-only
emitter previously returned a successful fsync receipt.

Repeated records remain visible one-for-one. Uncertainty remains visible and
is never silently upgraded or erased by later processing.

This module performs no writes, repairs, retries, resolver calls, network I/O,
authorization, remediation, or execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from veritas_os.audit.observable_digest_audit_emission import (
    ObservableDigestAuditEmissionError,
    ObservableDigestAuditEmissionReceipt,
)
from veritas_os.audit.observable_digest_audit_entry import (
    OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION,
)


SOURCE_PRESENT = "PRESENT"
SOURCE_MISSING = "MISSING"
SOURCE_READ_ERROR = "READ_ERROR"
SOURCE_REJECTED_DIRECTORY = "REJECTED_DIRECTORY"
SOURCE_REJECTED_SYMLINK = "REJECTED_SYMLINK"

LINE_RECONSTRUCTED = "RECONSTRUCTED"
LINE_EMPTY = "EMPTY_LINE"
LINE_INVALID_UTF8 = "INVALID_UTF8"
LINE_MALFORMED_JSON = "MALFORMED_JSON"
LINE_NON_OBJECT = "NON_OBJECT_RECORD"

EVIDENCE_RECEIPT_CONFIRMED = "RECEIPT_CONFIRMED"
EVIDENCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
LOCAL_DURABILITY_RECEIPT_CONFIRMED = "LOCAL_FSYNC_RECEIPT_CONFIRMED"

RECEIPT_MATCHED = "MATCHED"
RECEIPT_UNMATCHED = "UNMATCHED"

_FSYNC_COMPLETED = "fsync_completed"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class ObservableDigestAuditUncertainty:
    """Explicit uncertainty that must remain part of the audit story."""

    stage: str
    outcome: str
    path: str
    record_sha256: str
    bytes_written: int | None


def uncertainty_from_emission_error(
    error: ObservableDigestAuditEmissionError,
) -> ObservableDigestAuditUncertainty:
    """Capture an emission error as immutable verification input."""

    if not isinstance(error, ObservableDigestAuditEmissionError):
        raise TypeError("error must be ObservableDigestAuditEmissionError")
    return ObservableDigestAuditUncertainty(
        stage=error.stage,
        outcome=error.outcome,
        path=error.path,
        record_sha256=error.record_sha256,
        bytes_written=error.bytes_written,
    )


@dataclass(frozen=True)
class ObservableDigestAuditReconstructedLine:
    """One physical JSONL line, preserved in source order."""

    line_number: int
    status: str
    raw_sha256: str
    line_bytes: int
    canonical_sha256: str | None = None
    canonical_encoding_matches: bool | None = None
    canonical_json: str | None = None
    event_id: str | None = None
    schema_version: str | None = None
    schema_supported: bool | None = None
    emission_status: str = EVIDENCE_NOT_ESTABLISHED
    durability_status: str = EVIDENCE_NOT_ESTABLISHED
    matched_receipt_index: int | None = None

    @property
    def independently_reconstructable(self) -> bool:
        return self.status == LINE_RECONSTRUCTED

    def payload(self) -> dict[str, object] | None:
        """Return a fresh decoded payload copy when reconstruction succeeded."""

        if self.canonical_json is None:
            return None
        decoded = json.loads(self.canonical_json)
        if not isinstance(decoded, dict):
            return None
        return decoded


@dataclass(frozen=True)
class ObservableDigestAuditReceiptVerification:
    """Verification result for one explicitly supplied emission receipt."""

    receipt_index: int
    status: str
    event_id: str
    record_sha256: str
    matched_line_number: int | None
    reason: str | None


@dataclass(frozen=True)
class ObservableDigestAuditReconstructionReport:
    """Immutable read-only reconstruction result."""

    source_path: str
    source_status: str
    source_sha256: str | None
    source_order_preserved: bool
    physical_line_count: int
    absence_proven: bool
    lines: tuple[ObservableDigestAuditReconstructedLine, ...]
    receipts: tuple[ObservableDigestAuditReceiptVerification, ...]
    uncertainties: tuple[ObservableDigestAuditUncertainty, ...]

    @property
    def reconstructed_count(self) -> int:
        return sum(line.independently_reconstructable for line in self.lines)

    @property
    def malformed_count(self) -> int:
        return sum(not line.independently_reconstructable for line in self.lines)


def _report_without_source(
    *,
    path: Path,
    source_status: str,
    receipts: tuple[ObservableDigestAuditEmissionReceipt, ...],
    uncertainties: tuple[ObservableDigestAuditUncertainty, ...],
) -> ObservableDigestAuditReconstructionReport:
    receipt_results = tuple(
        ObservableDigestAuditReceiptVerification(
            receipt_index=index,
            status=RECEIPT_UNMATCHED,
            event_id=receipt.event_id,
            record_sha256=receipt.record_sha256,
            matched_line_number=None,
            reason="source_not_available",
        )
        for index, receipt in enumerate(receipts)
    )
    return ObservableDigestAuditReconstructionReport(
        source_path=str(path),
        source_status=source_status,
        source_sha256=None,
        source_order_preserved=False,
        physical_line_count=0,
        absence_proven=False,
        lines=(),
        receipts=receipt_results,
        uncertainties=uncertainties,
    )


def _reconstruct_line(
    *,
    line_number: int,
    raw_record: bytes,
    line_bytes: int,
) -> ObservableDigestAuditReconstructedLine:
    raw_hash = _sha256(raw_record)

    if not raw_record:
        return ObservableDigestAuditReconstructedLine(
            line_number=line_number,
            status=LINE_EMPTY,
            raw_sha256=raw_hash,
            line_bytes=line_bytes,
        )

    try:
        text = raw_record.decode("utf-8")
    except UnicodeDecodeError:
        return ObservableDigestAuditReconstructedLine(
            line_number=line_number,
            status=LINE_INVALID_UTF8,
            raw_sha256=raw_hash,
            line_bytes=line_bytes,
        )

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return ObservableDigestAuditReconstructedLine(
            line_number=line_number,
            status=LINE_MALFORMED_JSON,
            raw_sha256=raw_hash,
            line_bytes=line_bytes,
        )

    if not isinstance(decoded, dict):
        return ObservableDigestAuditReconstructedLine(
            line_number=line_number,
            status=LINE_NON_OBJECT,
            raw_sha256=raw_hash,
            line_bytes=line_bytes,
        )

    canonical = _canonical_json(decoded)
    canonical_bytes = canonical.encode("utf-8")
    event_id_value = decoded.get("event_id")
    schema_value = decoded.get("v1_schema_version")
    event_id = event_id_value if isinstance(event_id_value, str) else None
    schema_version = schema_value if isinstance(schema_value, str) else None

    return ObservableDigestAuditReconstructedLine(
        line_number=line_number,
        status=LINE_RECONSTRUCTED,
        raw_sha256=raw_hash,
        line_bytes=line_bytes,
        canonical_sha256=_sha256(canonical_bytes),
        canonical_encoding_matches=raw_record == canonical_bytes,
        canonical_json=canonical,
        event_id=event_id,
        schema_version=schema_version,
        schema_supported=(
            schema_version == OBSERVABLE_DIGEST_AUDIT_SCHEMA_VERSION
        ),
    )


def _receipt_exactly_matches(
    *,
    receipt: ObservableDigestAuditEmissionReceipt,
    receipt_path: str,
    line: ObservableDigestAuditReconstructedLine,
) -> bool:
    return (
        line.status == LINE_RECONSTRUCTED
        and line.canonical_encoding_matches is True
        and receipt.path == receipt_path
        and receipt.event_id == line.event_id
        and receipt.schema_version == line.schema_version
        and receipt.record_sha256 == line.raw_sha256
        and receipt.bytes_written == line.line_bytes
        and receipt.durability == _FSYNC_COMPLETED
    )


def _unmatched_receipt_reason(
    *,
    receipt: ObservableDigestAuditEmissionReceipt,
    source_path: str,
    lines: tuple[ObservableDigestAuditReconstructedLine, ...],
) -> str:
    if receipt.durability != _FSYNC_COMPLETED:
        return "unsupported_durability_claim"
    if receipt.path != source_path:
        return "source_path_mismatch"

    same_identity = tuple(
        line
        for line in lines
        if line.status == LINE_RECONSTRUCTED
        and line.event_id == receipt.event_id
        and line.schema_version == receipt.schema_version
    )
    if same_identity and all(
        line.raw_sha256 != receipt.record_sha256 for line in same_identity
    ):
        return "record_hash_mismatch"

    same_hash = tuple(
        line for line in lines if line.raw_sha256 == receipt.record_sha256
    )
    if same_hash and all(
        line.line_bytes != receipt.bytes_written for line in same_hash
    ):
        return "bytes_written_mismatch"

    return "no_exact_record_match"


def reconstruct_and_verify_observable_digest_audit(
    *,
    path: Path,
    receipts: Iterable[ObservableDigestAuditEmissionReceipt] = (),
    uncertainties: Iterable[ObservableDigestAuditUncertainty] = (),
) -> ObservableDigestAuditReconstructionReport:
    """Read and verify an observable-digest audit JSONL source without mutation.

    Successful reconstruction proves only current source visibility and
    parseability. Successful local emission/durability evidence is established
    only when an explicitly supplied successful receipt exactly matches one
    physical canonical JSONL record. Receipt matching is one-to-one so repeated
    records never inherit evidence from a single receipt.
    """

    if not isinstance(path, Path):
        raise TypeError("path must be pathlib.Path")

    receipt_tuple = tuple(receipts)
    for receipt in receipt_tuple:
        if not isinstance(receipt, ObservableDigestAuditEmissionReceipt):
            raise TypeError(
                "receipts must contain ObservableDigestAuditEmissionReceipt values"
            )

    uncertainty_tuple = tuple(uncertainties)
    for uncertainty in uncertainty_tuple:
        if not isinstance(uncertainty, ObservableDigestAuditUncertainty):
            raise TypeError(
                "uncertainties must contain ObservableDigestAuditUncertainty values"
            )

    if path.is_symlink():
        return _report_without_source(
            path=path,
            source_status=SOURCE_REJECTED_SYMLINK,
            receipts=receipt_tuple,
            uncertainties=uncertainty_tuple,
        )
    if not path.exists():
        return _report_without_source(
            path=path,
            source_status=SOURCE_MISSING,
            receipts=receipt_tuple,
            uncertainties=uncertainty_tuple,
        )
    if path.is_dir():
        return _report_without_source(
            path=path,
            source_status=SOURCE_REJECTED_DIRECTORY,
            receipts=receipt_tuple,
            uncertainties=uncertainty_tuple,
        )

    try:
        source_bytes = path.read_bytes()
    except OSError:
        return _report_without_source(
            path=path,
            source_status=SOURCE_READ_ERROR,
            receipts=receipt_tuple,
            uncertainties=uncertainty_tuple,
        )

    raw_lines = source_bytes.splitlines(keepends=True)
    if source_bytes and not raw_lines:
        raw_lines = [source_bytes]

    reconstructed: list[ObservableDigestAuditReconstructedLine] = []
    for line_number, raw_line_with_ending in enumerate(raw_lines, start=1):
        raw_record = (
            raw_line_with_ending[:-1]
            if raw_line_with_ending.endswith(b"\n")
            else raw_line_with_ending
        )
        reconstructed.append(
            _reconstruct_line(
                line_number=line_number,
                raw_record=raw_record,
                line_bytes=len(raw_line_with_ending),
            )
        )

    lines = tuple(reconstructed)
    used_receipts: set[int] = set()
    updated_lines: list[ObservableDigestAuditReconstructedLine] = []
    source_path = str(path)

    for line in lines:
        matched_index: int | None = None
        for index, receipt in enumerate(receipt_tuple):
            if index in used_receipts:
                continue
            if _receipt_exactly_matches(
                receipt=receipt,
                receipt_path=source_path,
                line=line,
            ):
                matched_index = index
                used_receipts.add(index)
                break

        if matched_index is None:
            updated_lines.append(line)
        else:
            updated_lines.append(
                replace(
                    line,
                    emission_status=EVIDENCE_RECEIPT_CONFIRMED,
                    durability_status=LOCAL_DURABILITY_RECEIPT_CONFIRMED,
                    matched_receipt_index=matched_index,
                )
            )

    final_lines = tuple(updated_lines)
    receipt_results: list[ObservableDigestAuditReceiptVerification] = []
    for index, receipt in enumerate(receipt_tuple):
        matched_line = next(
            (line.line_number for line in final_lines if line.matched_receipt_index == index),
            None,
        )
        if matched_line is not None:
            receipt_results.append(
                ObservableDigestAuditReceiptVerification(
                    receipt_index=index,
                    status=RECEIPT_MATCHED,
                    event_id=receipt.event_id,
                    record_sha256=receipt.record_sha256,
                    matched_line_number=matched_line,
                    reason=None,
                )
            )
        else:
            receipt_results.append(
                ObservableDigestAuditReceiptVerification(
                    receipt_index=index,
                    status=RECEIPT_UNMATCHED,
                    event_id=receipt.event_id,
                    record_sha256=receipt.record_sha256,
                    matched_line_number=None,
                    reason=_unmatched_receipt_reason(
                        receipt=receipt,
                        source_path=source_path,
                        lines=lines,
                    ),
                )
            )

    return ObservableDigestAuditReconstructionReport(
        source_path=source_path,
        source_status=SOURCE_PRESENT,
        source_sha256=_sha256(source_bytes),
        source_order_preserved=True,
        physical_line_count=len(raw_lines),
        absence_proven=False,
        lines=final_lines,
        receipts=tuple(receipt_results),
        uncertainties=uncertainty_tuple,
    )
