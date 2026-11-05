"""Durable *audit observation* registry for the #2446 local packet scanner.

This is NOT an authority registry or a runtime single-use gate. Its inputs are
only bounded local profiles re-validated by the existing offline scanner. A
recorded observation is self-declared, unsigned, and not an external effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from scripts.validation.cross_packet_replay_provenance import (
    verify_cross_packet_replay_provenance,
)
from scripts.validation.validate_audit_replay_observation_v0_1 import (
    calculate_observation_hash,
    verify_observation_contract,
)
from veritas_os.storage.db import get_pool

MAX_ARCHIVE_CASES = 32768


@dataclass(frozen=True)
class AuditArchiveResult:
    """An outcome scoped to this registry's observed local history only."""

    status: str
    packet_count: int = 0
    case_count: int = 0


class _ReplayConflict(Exception):
    """Triggers transaction rollback for any partial or conflicting archive."""


def _prepare_packets(
    packet_root: Path | str, profile_paths: Sequence[str],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Re-run the scanner; never accept self-asserted PASS or raw records."""
    report = verify_cross_packet_replay_provenance(
        packet_root=packet_root, profile_paths=profile_paths,
    )
    if report["status"] == "REPLAY_DETECTED":
        raise _ReplayConflict
    if report["status"] != "PASS":
        raise ValueError("LOCAL_SCAN_NOT_PASS")
    packets = report["packet_records"]
    links = report["link_records"]
    if (
        not packets or not links or len(links) > MAX_ARCHIVE_CASES
        or len(packets) != report["input_count"]
        or len(links) != report["bound_case_count"]
    ):
        raise ValueError("INCOMPLETE_SCAN_INVENTORY")

    by_path = {packet["path"]: [] for packet in packets}
    if len(by_path) != len(packets):
        raise ValueError("DUPLICATE_PACKET_PATH")
    packet_index = {packet["path"]: packet for packet in packets}
    for link in links:
        packet = packet_index.get(link["path"])
        if (
            packet is None or link["repository"] != packet["repository"]
            or link["source_commit"] != packet["source_commit"]
            or link["packet_id"] != packet["packet_id"]
        ):
            raise ValueError("MISMATCHED_SCANNER_LINK")
        record = {
            "format_version": "veritas.audit-replay-observation/0.1",
            "record_type": "LOCAL_AUDIT_OBSERVATION",
            "packet_id": packet["packet_id"],
            "case_id": link["case_id"],
            "repository_claim": packet["repository"],
            "repository_key": packet["repository"].lower(),
            "source_commit": packet["source_commit"],
            "operation_id": link["operation_id"],
            "manifest_id": link["manifest_id"],
            "profile_sha256": packet["profile_sha256"],
            "manifest_sha256": link["manifest_sha256"],
            "snapshot_digest": report["snapshot_digest"],
            "local_manifest_binding": link["local_manifest_binding"],
            "declared_provenance_binding": link["declared_provenance_binding"],
            "origin_authentication": link["origin_authentication"],
            "independent_review": link["independent_review"],
        }
        record["record_hash"] = calculate_observation_hash(record)
        if verify_observation_contract(record):
            raise ValueError("INVALID_LOCAL_OBSERVATION")
        by_path[link["path"]].append(record)

    output = []
    for packet in packets:
        cases = by_path[packet["path"]]
        if not cases or len({c["case_id"] for c in cases}) != len(cases):
            raise ValueError("INVALID_LOCAL_CASE_INVENTORY")
        header = {
            "packet_id": packet["packet_id"],
            "profile_sha256": packet["profile_sha256"],
            "repository_claim": packet["repository"],
            "repository_key": packet["repository"].lower(),
            "source_commit": packet["source_commit"],
            "snapshot_digest": report["snapshot_digest"],
            "case_count": len(cases),
        }
        output.append((header, sorted(cases, key=lambda c: c["case_id"])))
    return output


_PACKET_QUERY = (
    "SELECT packet_id, profile_sha256, repository_claim, repository_key, "
    "source_commit, snapshot_digest, case_count "
    "FROM audit_packet_inventory WHERE packet_id = %s"
)
_CASE_QUERY = (
    "SELECT record FROM audit_case_observations "
    "WHERE packet_id = %s ORDER BY case_id"
)
_HEADER_KEYS = (
    "packet_id", "profile_sha256", "repository_claim", "repository_key",
    "source_commit", "snapshot_digest", "case_count",
)


class PostgresAuditReplayRegistry:
    """Separate from real Bind Authorization consumption and effects."""

    async def ingest(
        self, *, packet_root: Path | str, profile_paths: Sequence[str],
    ) -> AuditArchiveResult:
        try:
            batch = _prepare_packets(packet_root, profile_paths)
        except _ReplayConflict:
            return AuditArchiveResult("REPLAY_DETECTED")
        except (TypeError, ValueError, KeyError, OSError, RecursionError, OverflowError):
            return AuditArchiveResult("INPUT_INVALID")

        new_count = 0
        existing_count = 0
        case_count = sum(len(cases) for _, cases in batch)
        try:
            from psycopg.types.json import Jsonb

            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    for header, cases in batch:
                        cur = await conn.execute(
                            "INSERT INTO audit_packet_inventory "
                            "(packet_id, profile_sha256, repository_claim, repository_key, "
                            "source_commit, snapshot_digest, case_count) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                            "ON CONFLICT DO NOTHING RETURNING packet_id",
                            tuple(header[key] for key in _HEADER_KEYS),
                        )
                        inserted = await cur.fetchone()
                        if inserted is None:
                            # ON CONFLICT waits on an uncommitted competing
                            # insert before returning. Read committed state
                            # and compare exact immutable batch contents.
                            cur = await conn.execute(_PACKET_QUERY, (header["packet_id"],))
                            found = await cur.fetchone()
                            if found is None or dict(zip(_HEADER_KEYS, found)) != header:
                                raise _ReplayConflict
                            cur = await conn.execute(_CASE_QUERY, (header["packet_id"],))
                            rows = await cur.fetchall()
                            if [r[0] for r in rows] != cases:
                                raise _ReplayConflict
                            existing_count += 1
                            continue

                        new_count += 1
                        for record in cases:
                            cur = await conn.execute(
                                "INSERT INTO audit_case_observations "
                                "(record_hash, packet_id, case_id, repository_key, "
                                "operation_id, manifest_id, manifest_sha256, record) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                                "ON CONFLICT DO NOTHING RETURNING record_hash",
                                (
                                    record["record_hash"], record["packet_id"],
                                    record["case_id"], record["repository_key"],
                                    record["operation_id"], record["manifest_id"],
                                    record["manifest_sha256"], Jsonb(record),
                                ),
                            )
                            if await cur.fetchone() is None:
                                raise _ReplayConflict
                    # Mixed old and new in a single scanner batch is ambiguous
                    # (neither wholly new nor an exact retry). Roll back all.
                    if new_count and existing_count:
                        raise _ReplayConflict
            return AuditArchiveResult(
                "NEW_OBSERVATION" if new_count else "ALREADY_PRESENT",
                packet_count=len(batch), case_count=case_count,
            )
        except _ReplayConflict:
            return AuditArchiveResult("REPLAY_DETECTED")
        except Exception:
            # Connection, permission, transaction/commit ambiguity and
            # operational DB errors must never be reported as a clean PASS.
            return AuditArchiveResult("REGISTRY_UNAVAILABLE")

    async def readback(self, packet_id: str) -> tuple[str, list[dict[str, Any]]]:
        """Read retained observations; not a historical completeness claim."""
        if not isinstance(packet_id, str) or not packet_id.strip():
            return "INPUT_INVALID", []
        try:
            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    cur = await conn.execute(_PACKET_QUERY, (packet_id,))
                    header_row = await cur.fetchone()
                    if header_row is None:
                        return "NOT_FOUND", []
                    header = dict(zip(_HEADER_KEYS, header_row))
                    cur = await conn.execute(_CASE_QUERY, (packet_id,))
                    records = [row[0] for row in await cur.fetchall()]
            if len(records) != header["case_count"]:
                return "INCOMPLETE", []
            for item in records:
                if (
                    verify_observation_contract(item)
                    or item["packet_id"] != header["packet_id"]
                    or item["profile_sha256"] != header["profile_sha256"]
                    or item["repository_claim"] != header["repository_claim"]
                    or item["repository_key"] != header["repository_key"]
                    or item["source_commit"] != header["source_commit"]
                    or item["snapshot_digest"] != header["snapshot_digest"]
                ):
                    return "INCOMPLETE", []
            return "FOUND_UNAUTHENTICATED", records
        except Exception:
            return "REGISTRY_UNAVAILABLE", []
