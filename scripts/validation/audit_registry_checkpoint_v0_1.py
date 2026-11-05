"""Bounded, opt-in snapshots of the local PostgreSQL audit inventory.

A caller must retain the checkpoint AND pin its SHA-256 independently of the
registry. These unsigned local observations do not establish issuer identity,
global history completeness, WORM custody or execution permission.
"""
from __future__ import annotations

import hmac
import re
from typing import Any

from scripts.validation.validate_audit_replay_observation_v0_1 import (
    verify_observation_contract,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.db import get_pool

MAX_CHECKPOINT_PACKETS = 64
MAX_CHECKPOINT_CASES = 1024
MAX_RECORD_STORAGE_BYTES = 32768
_FORMAT = "veritas.audit-registry-checkpoint/0.1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CHECKPOINT_KEYS = {
    "format_version", "scope", "packet_count", "case_count", "packets",
    "snapshot_root", "origin_authentication", "external_anchor",
    "checkpoint_hash",
}
_HEADER_KEYS = (
    "packet_id", "profile_sha256", "repository_claim", "repository_key",
    "source_commit", "snapshot_digest", "case_count",
)
_CASE_KEYS = (
    "record_hash", "packet_id", "case_id", "repository_key",
    "operation_id", "manifest_id", "manifest_sha256", "record",
)


def _digest(value: Any) -> str:
    return sha256_of_canonical_json(value)


def validate_checkpoint(value: Any) -> bool:
    """Validate structure, ordering, digest, scope and bounded roster."""
    if not isinstance(value, dict) or set(value) != _CHECKPOINT_KEYS:
        return False
    if (
        value["format_version"] != _FORMAT
        or value["scope"] != "LOCAL_UNAUTHENTICATED_AUDIT_INVENTORY"
        or value["origin_authentication"] != "NOT_PERFORMED"
        or value["external_anchor"] != "NOT_EMBEDDED"
        or type(value["packet_count"]) is not int
        or type(value["case_count"]) is not int
        or not 1 <= value["packet_count"] <= MAX_CHECKPOINT_PACKETS
        or not 1 <= value["case_count"] <= MAX_CHECKPOINT_CASES
        or not isinstance(value["packets"], list)
        or len(value["packets"]) != value["packet_count"]
        or not isinstance(value["snapshot_root"], str)
        or not _SHA.fullmatch(value["snapshot_root"])
        or not isinstance(value["checkpoint_hash"], str)
        or not _SHA.fullmatch(value["checkpoint_hash"])
    ):
        return False
    seen = set()
    total = 0
    previous = ""
    for entry in value["packets"]:
        if not isinstance(entry, dict) or set(entry) != {
            "packet_id", "packet_hash", "case_count",
        }:
            return False
        packet_id = entry["packet_id"]
        if (
            not isinstance(packet_id, str)
            or not packet_id
            or len(packet_id) > 256
            or packet_id <= previous
            or packet_id in seen
            or not isinstance(entry["packet_hash"], str)
            or not _SHA.fullmatch(entry["packet_hash"])
            or type(entry["case_count"]) is not int
            or not 1 <= entry["case_count"] <= MAX_CHECKPOINT_CASES
        ):
            return False
        seen.add(packet_id)
        previous = packet_id
        total += entry["case_count"]
    if total != value["case_count"]:
        return False
    root_input = {
        "format_version": _FORMAT,
        "packet_count": value["packet_count"],
        "case_count": value["case_count"],
        "packets": value["packets"],
    }
    if value["snapshot_root"] != _digest(root_input):
        return False
    content = {k: v for k, v in value.items() if k != "checkpoint_hash"}
    return hmac.compare_digest(value["checkpoint_hash"], _digest(content))


def compare_pinned_checkpoint(
    *, current: dict[str, Any], reference: Any, pinned_reference_sha256: str,
) -> str:
    """Compare a DB-derived checkpoint to an independently pinned baseline.

    This pure comparator does NOT authenticate either input; the caller must
    obtain current via capture_checkpoint() and protect the reference digest
    outside the database and outside the untrusted reference document.
    """
    if not isinstance(pinned_reference_sha256, str) or not _SHA.fullmatch(
        pinned_reference_sha256
    ):
        return "ANCHOR_REQUIRED"
    if not validate_checkpoint(reference):
        return "REFERENCE_INVALID"
    if not hmac.compare_digest(
        _digest(reference), pinned_reference_sha256,
    ):
        return "REFERENCE_ANCHOR_MISMATCH"
    if not validate_checkpoint(current):
        return "INCOMPLETE"
    original = {e["packet_id"]: e for e in reference["packets"]}
    observed = {e["packet_id"]: e for e in current["packets"]}
    if any(observed.get(packet_id) != packet for packet_id, packet in original.items()):
        return "HISTORY_DIVERGED"
    if len(observed) == len(original):
        return "HISTORY_UNCHANGED_UNAUTHENTICATED"
    return "HISTORY_EXTENDED_UNAUTHENTICATED"


def _verified_case(case_row: tuple[Any, ...], header: dict[str, Any]) -> dict[str, Any]:
    row = dict(zip(_CASE_KEYS, case_row))
    record = row["record"]
    if not isinstance(record, dict) or verify_observation_contract(record):
        raise ValueError("CORRUPT_RECORD")
    for col in _CASE_KEYS[:-1]:
        if record[col] != row[col]:
            raise ValueError("MISMATCHED_CASE_COLUMN")
    for col in _HEADER_KEYS[:-1]:
        if col in record and record[col] != header[col]:
            raise ValueError("MISMATCHED_PACKET_HEADER")
    if record["snapshot_digest"] != header["snapshot_digest"]:
        raise ValueError("MISMATCHED_SNAPSHOT")
    if record["profile_sha256"] != header["profile_sha256"]:
        raise ValueError("MISMATCHED_PROFILE")
    if record["source_commit"] != header["source_commit"]:
        raise ValueError("MISMATCHED_SOURCE_COMMIT")
    if record["repository_claim"] != header["repository_claim"]:
        raise ValueError("MISMATCHED_REPOSITORY")
    return record


async def capture_checkpoint() -> tuple[str, dict[str, Any] | None]:
    """Read a consistent *whole bounded registry* snapshot; never truncate.

    REPEATABLE READ with READ ONLY is required so concurrent ingest cannot
    produce a torn checkpoint across the packet/case tables.
    """
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                cursor = await conn.execute(
                    "SELECT packet_id, profile_sha256, repository_claim, "
                    "repository_key, source_commit, snapshot_digest, case_count "
                    "FROM audit_packet_inventory ORDER BY packet_id LIMIT %s",
                    (MAX_CHECKPOINT_PACKETS + 1,),
                )
                headers = await cursor.fetchall()
                if not headers or len(headers) > MAX_CHECKPOINT_PACKETS:
                    return "INCOMPLETE", None
                total = 0
                roster: list[dict[str, Any]] = []
                for values in headers:
                    header = dict(zip(_HEADER_KEYS, values))
                    count = header["case_count"]
                    if type(count) is not int or not 1 <= count <= MAX_CHECKPOINT_CASES:
                        return "INCOMPLETE", None
                    if total + count > MAX_CHECKPOINT_CASES:
                        return "INCOMPLETE", None
                    if (
                        not isinstance(header["packet_id"], str)
                        or not 0 < len(header["packet_id"]) <= 256
                    ):
                        return "INCOMPLETE", None
                    cursor = await conn.execute(
                        "SELECT record_hash, packet_id, case_id, repository_key, "
                        "operation_id, manifest_id, manifest_sha256, "
                        "CASE WHEN pg_column_size(record) <= %s "
                        "THEN record ELSE NULL END "
                        "FROM audit_case_observations WHERE packet_id = %s "
                        "ORDER BY case_id LIMIT %s",
                        (
                            MAX_RECORD_STORAGE_BYTES, header["packet_id"],
                            count + 1,
                        ),
                    )
                    rows = await cursor.fetchall()
                    if len(rows) != count:
                        return "INCOMPLETE", None
                    records = [_verified_case(row, header) for row in rows]
                    if len({record["case_id"] for record in records}) != len(records):
                        return "INCOMPLETE", None
                    case_hashes = [
                        {"case_id": r["case_id"], "record_hash": r["record_hash"]}
                        for r in records
                    ]
                    roster.append({
                        "packet_id": header["packet_id"],
                        "packet_hash": _digest({
                            "header": header, "cases": case_hashes,
                        }),
                        "case_count": count,
                    })
                    total += count
                cursor = await conn.execute(
                    "SELECT count(*) FROM audit_case_observations"
                )
                result = await cursor.fetchone()
                if result is None or result[0] != total:
                    return "INCOMPLETE", None
        root_input = {
            "format_version": _FORMAT,
            "packet_count": len(roster),
            "case_count": total,
            "packets": roster,
        }
        checkpoint = {
            **root_input,
            "scope": "LOCAL_UNAUTHENTICATED_AUDIT_INVENTORY",
            "origin_authentication": "NOT_PERFORMED",
            "external_anchor": "NOT_EMBEDDED",
            "snapshot_root": _digest(root_input),
        }
        checkpoint["checkpoint_hash"] = _digest(checkpoint)
        if not validate_checkpoint(checkpoint):
            return "INCOMPLETE", None
        return "SNAPSHOT_READY_UNAUTHENTICATED", checkpoint
    except ValueError:
        return "INCOMPLETE", None
    except Exception:
        return "REGISTRY_UNAVAILABLE", None


async def check_registry_against_pin(
    *, reference: Any, pinned_reference_sha256: str,
) -> str:
    """Require a supplied separately pinned SHA before accessing the DB."""
    if not isinstance(pinned_reference_sha256, str) or not _SHA.fullmatch(
        pinned_reference_sha256
    ):
        return "ANCHOR_REQUIRED"
    if not validate_checkpoint(reference):
        return "REFERENCE_INVALID"
    if not hmac.compare_digest(_digest(reference), pinned_reference_sha256):
        return "REFERENCE_ANCHOR_MISMATCH"
    status, current = await capture_checkpoint()
    if status != "SNAPSHOT_READY_UNAUTHENTICATED" or current is None:
        return status
    return compare_pinned_checkpoint(
        current=current, reference=reference,
        pinned_reference_sha256=pinned_reference_sha256,
    )
