"""VERITAS OS — File-to-PostgreSQL import/migration CLI.

Safely migrates data from the file-based backends (JSON Memory and JSONL
TrustLog) to the PostgreSQL backend.  The tool is designed to be:

* **Idempotent** — re-running produces the same final state.  Entries
  already present in PostgreSQL are skipped (duplicate-safe).
* **Fail-soft** — a single malformed or failing entry is recorded in the
  report but does not abort the migration.
* **Chain-preserving** — TrustLog ``sha256`` / ``sha256_prev`` values are
  stored verbatim; the hash chain is *never* recomputed.
* **Observable** — every run produces a structured report with counts for
  migrated, duplicates, malformed, failed, and (optionally) verify result.

Usage
-----
Dry-run (no writes)::

    veritas-migrate memory   --source /data/logs/memory.json   --dry-run
    veritas-migrate trustlog --source /data/logs/trust_log.jsonl --dry-run

Production migration::

    veritas-migrate memory   --source /data/logs/memory.json
    veritas-migrate trustlog --source /data/logs/trust_log.jsonl

With post-migration hash-chain verification::

    veritas-migrate trustlog --source /data/logs/trust_log.jsonl --verify

JSON output (for CI pipelines)::

    veritas-migrate memory --source memory.json --dry-run --json

Exit codes
----------
0  Migration completed with zero failures (or dry-run finished cleanly).
1  Migration completed but some entries failed or malformed entries found.
2  Invalid arguments or fatal runtime error.

Security note
-------------
The migration tool should be run while TrustLog writes are paused (service
stopped or quiesced) to avoid interleaving new entries with migrated ones.
Running concurrently with an active TrustLog backend is safe for the
*Memory* migration but may produce non-sequential chain IDs for TrustLog.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Migration report
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MigrationReport:
    """Structured result of a single migration run.

    Attributes:
        source: Path to the source file (for traceability).
        migrated: Entries successfully written to PostgreSQL.
        skipped: Entries intentionally skipped (e.g. validation filter).
        duplicates: Entries already present in PostgreSQL; not overwritten.
        malformed: Entries that could not be parsed or lacked required fields.
        failed: Entries that triggered a database or infrastructure error.
        dry_run: ``True`` when no writes were performed.
        verify_ok: ``True``/``False`` when ``--verify`` was requested;
            ``None`` otherwise.
        verify_detail: Raw verification result dict when verify was run.
        errors: Human-readable descriptions of individual malformed/failed
            entries (capped at 200 to bound memory usage).
    """

    source: str = ""
    migrated: int = 0
    skipped: int = 0
    duplicates: int = 0
    malformed: int = 0
    failed: int = 0
    dry_run: bool = False
    verify_ok: Optional[bool] = None
    verify_detail: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    # Maximum number of individual error messages retained per report.
    _MAX_ERRORS: int = 200

    def total_processed(self) -> int:
        """Total entries encountered in the source file."""
        return self.migrated + self.skipped + self.duplicates + self.malformed + self.failed

    def success(self) -> bool:
        """Return ``True`` when migration completed with zero hard failures."""
        return self.failed == 0 and self.malformed == 0

    def _add_error(self, msg: str) -> None:
        """Append *msg* to the error list, respecting the cap."""
        if len(self.errors) < self._MAX_ERRORS:
            self.errors.append(msg)


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL chain verifier (subset — chains only, no signature check)
# ─────────────────────────────────────────────────────────────────────────────


async def _verify_pg_trustlog_chain() -> Dict[str, Any]:
    """Verify the hash-chain integrity of TrustLog entries in PostgreSQL.

    Iterates all rows in ``trustlog_entries`` (ordered by ``id``) and checks
    that each entry's ``sha256_prev`` field matches the previous entry's
    ``sha256`` field.

    Returns:
        A dict with keys: ``ok``, ``total_entries``, ``valid_entries``,
        ``invalid_entries``, ``errors`` (list of per-entry dicts).
    """
    from veritas_os.storage.postgresql import PostgresTrustLogStore  # noqa: PLC0415

    pg = PostgresTrustLogStore()

    prev_hash: Optional[str] = None
    total = 0
    valid = 0
    chain_errors: List[Dict[str, Any]] = []

    offset = 0
    page_size = 1000

    while True:
        batch: List[Dict[str, Any]] = []
        async for entry in pg.iter_entries(limit=page_size, offset=offset):
            batch.append(entry)

        if not batch:
            break

        for entry in batch:
            total += 1
            actual_prev = entry.get("sha256_prev")

            if prev_hash is not None and actual_prev != prev_hash:
                if len(chain_errors) < 50:
                    chain_errors.append(
                        {
                            "index": total - 1,
                            "reason": "sha256_prev_mismatch",
                            "expected_prefix": str(prev_hash)[:16],
                            "actual_prefix": str(actual_prev)[:16],
                        }
                    )
            else:
                valid += 1

            prev_hash = entry.get("sha256")

        offset += len(batch)
        if len(batch) < page_size:
            break

    ok = len(chain_errors) == 0
    return {
        "ok": ok,
        "total_entries": total,
        "valid_entries": valid,
        "invalid_entries": len(chain_errors),
        "errors": chain_errors,
        "source": "postgresql",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Memory migration
# ─────────────────────────────────────────────────────────────────────────────


async def _migrate_memory(
    source_path: Path,
    *,
    dry_run: bool,
    batch_size: int,
) -> MigrationReport:
    """Migrate all records from the JSON Memory backend to PostgreSQL.

    Reads every record from *source_path* (regardless of ``user_id``) and
    inserts it into ``memory_records`` using skip-on-conflict semantics.
    Re-running is safe: existing ``(key, user_id)`` pairs are counted as
    duplicates and not overwritten.

    The source file is read directly (not through ``MemoryStore``) so that
    individual malformed records can be skipped without aborting the whole
    migration.  Both the list format (current) and the legacy
    ``{"users": {...}}`` dict format are supported.

    Args:
        source_path: Path to ``memory.json`` (or equivalent JSON file).
        dry_run: When ``True``, report scope without writing.
        batch_size: Reserved for future chunked I/O; not used currently.

    Returns:
        A :class:`MigrationReport` describing the outcome.
    """
    from veritas_os.storage.postgresql import PostgresMemoryStore  # noqa: PLC0415

    report = MigrationReport(source=str(source_path), dry_run=dry_run)

    if not source_path.exists():
        report._add_error(f"source not found: {source_path}")
        report.failed += 1
        return report

    # ── Load source JSON directly for per-record error isolation ──────────
    try:
        with source_path.open("r", encoding="utf-8") as fh:
            raw_json: Any = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load memory source %s: %s", source_path, exc)
        report._add_error(f"load_error: {exc}")
        report.failed += 1
        return report

    # Normalise to a flat list of record dicts.
    if isinstance(raw_json, list):
        records: List[Any] = raw_json
    elif isinstance(raw_json, dict) and "users" in raw_json:
        # Legacy dict format: {"users": {"user_id": {"key": value, ...}}}
        users = raw_json.get("users") or {}
        flat: List[Dict[str, Any]] = []
        if isinstance(users, dict):
            import time as _time  # noqa: PLC0415

            for uid, udata in users.items():
                if isinstance(udata, dict):
                    for k, v in udata.items():
                        flat.append(
                            {
                                "user_id": uid,
                                "key": k,
                                "value": v,
                                "ts": _time.time(),
                            }
                        )
        records = flat
    elif isinstance(raw_json, dict) and "items" in raw_json:
        # Alternate format: {"items": [...]}
        records = raw_json.get("items") or []
    else:
        report._add_error(f"unrecognised source format: {type(raw_json).__name__}")
        report.failed += 1
        return report

    pg = PostgresMemoryStore()

    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            report.malformed += 1
            report._add_error(f"record[{idx}] not a dict: {type(record).__name__}")
            continue

        key = record.get("key")
        user_id = record.get("user_id")
        value = record.get("value")

        if not key or not user_id:
            report.malformed += 1
            report._add_error(
                f"record[{idx}] missing required field "
                f"(key={key!r}, user_id={user_id!r})"
            )
            continue

        if not isinstance(value, dict):
            # Normalise non-dict values to an empty dict rather than failing.
            value = {}

        try:
            inserted = await pg.import_record(
                key=str(key),
                value=value,
                user_id=str(user_id),
                dry_run=dry_run,
            )
            if inserted:
                report.migrated += 1
            else:
                report.duplicates += 1
        except Exception as exc:
            logger.warning(
                "Failed to import memory record[%d] key=%r user_id=%r: %s",
                idx,
                key,
                user_id,
                exc,
            )
            report.failed += 1
            report._add_error(f"record[{idx}] key={key!r} user_id={user_id!r}: {exc}")

    return report


# ─────────────────────────────────────────────────────────────────────────────
# TrustLog migration
# ─────────────────────────────────────────────────────────────────────────────


async def _migrate_trustlog(
    source_path: Path,
    *,
    dry_run: bool,
    verify: bool,
    batch_size: int,
) -> MigrationReport:
    """Migrate all entries from the JSONL TrustLog backend to PostgreSQL.

    Reads *source_path* line-by-line (decrypting ``ENC:`` prefixed lines
    automatically when ``VERITAS_ENCRYPTION_KEY`` is set).  Each entry is
    inserted into ``trustlog_entries`` with its **original** ``sha256`` /
    ``sha256_prev`` / ``request_id`` values preserved verbatim.  The
    ``prepare_entry`` pipeline is **not** invoked — this is a structural
    import, not a re-processing pass.

    Duplicate detection uses the ``request_id`` unique constraint; entries
    with a matching ``request_id`` already present in PostgreSQL are skipped.

    When *verify* is ``True`` and the run is not a dry-run, a hash-chain
    integrity check is performed against the PostgreSQL backend after all
    entries have been imported.

    Args:
        source_path: Path to ``trust_log.jsonl`` (plain or encrypted JSONL).
        dry_run: When ``True``, report scope without writing.
        verify: Run post-migration hash-chain verification on PostgreSQL.
        batch_size: Reserved for future streaming support; not used currently.

    Returns:
        A :class:`MigrationReport` describing the outcome.
    """
    from veritas_os.logging.encryption import (  # noqa: PLC0415
        decrypt as _decrypt_line,
        DecryptionError,
        EncryptionKeyMissing,
    )
    from veritas_os.storage.postgresql import PostgresTrustLogStore  # noqa: PLC0415

    report = MigrationReport(source=str(source_path), dry_run=dry_run)

    if not source_path.exists():
        report._add_error(f"source not found: {source_path}")
        report.failed += 1
        return report

    pg = PostgresTrustLogStore()
    line_idx = 0

    try:
        with source_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue

                # ── Decrypt if needed ──────────────────────────────────────
                try:
                    decoded = _decrypt_line(line)
                    entry = json.loads(decoded)
                except EncryptionKeyMissing as exc:
                    report.malformed += 1
                    report._add_error(f"line[{line_idx}] key_missing: {exc}")
                    line_idx += 1
                    continue
                except DecryptionError as exc:
                    report.malformed += 1
                    report._add_error(f"line[{line_idx}] decrypt_failed: {exc}")
                    line_idx += 1
                    continue
                except (json.JSONDecodeError, ValueError) as exc:
                    report.malformed += 1
                    report._add_error(f"line[{line_idx}] json_error: {exc}")
                    line_idx += 1
                    continue

                if not isinstance(entry, dict):
                    report.malformed += 1
                    report._add_error(
                        f"line[{line_idx}] not_a_dict: {type(entry).__name__}"
                    )
                    line_idx += 1
                    continue

                # ── Require at least one unique identifier ─────────────────
                request_id = entry.get("request_id") or entry.get("sha256")
                if not request_id:
                    report.malformed += 1
                    report._add_error(
                        f"line[{line_idx}] missing 'request_id' and 'sha256'"
                    )
                    line_idx += 1
                    continue

                # ── Import ────────────────────────────────────────────────
                try:
                    _rid, inserted = await pg.import_entry(entry, dry_run=dry_run)
                    if inserted:
                        report.migrated += 1
                    else:
                        report.duplicates += 1
                except ValueError as exc:
                    report.malformed += 1
                    report._add_error(f"line[{line_idx}] value_error: {exc}")
                except Exception as exc:
                    logger.warning(
                        "Failed to import trustlog line[%d] request_id=%r: %s",
                        line_idx,
                        request_id,
                        exc,
                    )
                    report.failed += 1
                    report._add_error(f"line[{line_idx}] failed: {exc}")

                line_idx += 1

    except OSError as exc:
        logger.error("Failed to read TrustLog source %s: %s", source_path, exc)
        report._add_error(f"read_error: {exc}")
        report.failed += 1
        return report

    # ── Post-migration verification ────────────────────────────────────────
    if verify and not dry_run:
        try:
            verify_result = await _verify_pg_trustlog_chain()
            report.verify_ok = verify_result.get("ok", False)
            report.verify_detail = verify_result
        except Exception as exc:
            logger.warning("Post-migration verify failed: %s", exc)
            report.verify_ok = False
            report.verify_detail = {"ok": False, "error": str(exc)}

    return report


# ─────────────────────────────────────────────────────────────────────────────
# Report formatting
# ─────────────────────────────────────────────────────────────────────────────


def _format_report(report: MigrationReport, *, output_json: bool) -> str:
    """Render *report* as human-readable text or a JSON string."""
    if output_json:
        return json.dumps(asdict(report), indent=2, default=str)

    lines: List[str] = [
        "=" * 60,
        "VERITAS OS Migration Report",
        "=" * 60,
        f"  Source:     {report.source}",
        f"  Dry-run:    {report.dry_run}",
        "",
        f"  Migrated:   {report.migrated}",
        f"  Duplicates: {report.duplicates}",
        f"  Skipped:    {report.skipped}",
        f"  Malformed:  {report.malformed}",
        f"  Failed:     {report.failed}",
        f"  Total:      {report.total_processed()}",
    ]

    if report.verify_ok is not None:
        lines.append(f"  Verify:     {'PASS' if report.verify_ok else 'FAIL'}")

    if report.errors:
        shown = min(len(report.errors), 20)
        lines += ["", f"  Errors ({shown}/{len(report.errors)}):"]
        for e in report.errors[:shown]:
            lines.append(f"    - {e}")
        if len(report.errors) > shown:
            lines.append(f"    ... and {len(report.errors) - shown} more")

    lines += [
        "=" * 60,
        "Status: " + ("PASS" if report.success() else "FAIL"),
        "=" * 60,
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veritas-migrate",
        description=(
            "VERITAS OS file-to-PostgreSQL migration tool. "
            "Migrates JSON Memory and JSONL TrustLog data to PostgreSQL "
            "idempotently with dry-run support."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  veritas-migrate memory   --source memory.json --dry-run\n"
            "  veritas-migrate trustlog --source trust_log.jsonl --verify\n"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output migration report as JSON.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ── memory ────────────────────────────────────────────────────────────
    mem_p = sub.add_parser(
        "memory",
        help="Migrate JSON Memory file to PostgreSQL.",
        description="Migrate memory.json records to the PostgreSQL memory_records table.",
    )
    mem_p.add_argument(
        "--source",
        type=Path,
        required=True,
        metavar="FILE",
        help="Path to source memory.json file.",
    )
    mem_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing to PostgreSQL.",
    )
    mem_p.add_argument(
        "--batch-size",
        type=int,
        default=500,
        metavar="N",
        help="Processing batch size (default: 500; reserved for future use).",
    )
    mem_p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output migration report as JSON.",
    )

    # ── trustlog ──────────────────────────────────────────────────────────
    tl_p = sub.add_parser(
        "trustlog",
        help="Migrate JSONL TrustLog file to PostgreSQL.",
        description=(
            "Migrate trust_log.jsonl entries to the PostgreSQL trustlog_entries "
            "table, preserving original sha256/sha256_prev chain hashes verbatim."
        ),
    )
    tl_p.add_argument(
        "--source",
        type=Path,
        required=True,
        metavar="FILE",
        help="Path to source trust_log.jsonl file (plain or encrypted).",
    )
    tl_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing to PostgreSQL.",
    )
    tl_p.add_argument(
        "--verify",
        action="store_true",
        help="Run hash-chain integrity check on PostgreSQL after migration.",
    )
    tl_p.add_argument(
        "--batch-size",
        type=int,
        default=500,
        metavar="N",
        help="Processing batch size (default: 500; reserved for future use).",
    )
    tl_p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output migration report as JSON.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for the VERITAS migration tool.

    Returns:
        Exit code: 0 = success, 1 = partial failure, 2 = fatal error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        if args.command == "memory":
            report = asyncio.run(
                _migrate_memory(
                    args.source,
                    dry_run=args.dry_run,
                    batch_size=args.batch_size,
                )
            )
        elif args.command == "trustlog":
            report = asyncio.run(
                _migrate_trustlog(
                    args.source,
                    dry_run=args.dry_run,
                    verify=args.verify,
                    batch_size=args.batch_size,
                )
            )
        else:
            # Unreachable via argparse; defensive guard.
            print(f"ERROR: unknown command {args.command!r}", file=sys.stderr)
            return 2

    except Exception as exc:
        msg = f"Migration error: {exc.__class__.__name__}: {exc}"
        if getattr(args, "output_json", False):
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    print(_format_report(report, output_json=args.output_json))
    return 0 if report.success() else 1


if __name__ == "__main__":
    sys.exit(main())
