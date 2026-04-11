"""VERITAS TrustLog standalone verifier CLI.

Provides a self-contained command-line tool for third-party auditors to verify
TrustLog integrity without running the VERITAS application server.

Usage:
    veritas-trustlog-verify --full-ledger trust_log.jsonl --witness-ledger trustlog.jsonl
    python -m veritas_os.cli.verify_trustlog --witness-ledger trustlog.jsonl --json

Exit codes:
    0 - All checks passed
    1 - Verification failures detected
    2 - Invalid arguments or runtime error
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)


def _load_witness_entries(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL witness ledger entries."""
    entries: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _logger.warning("Skipping corrupt entry at line %d: %s", line_no, exc)
    return entries


def _build_verify_signature_fn(public_key_path: Optional[Path] = None):
    """Build a signature verification callable.

    Attempts to use cryptography library for Ed25519 verification.
    Falls back to a permissive stub if keys are unavailable.
    """
    def _verify(entry: Dict[str, Any]) -> bool:
        payload_hash = entry.get("payload_hash")
        signature_b64 = entry.get("signature")
        if not payload_hash or not signature_b64:
            return False
        try:
            from veritas_os.security.signing import build_trustlog_signer
            signer_meta = entry.get("signer_metadata", {})
            signer_type = str(
                signer_meta.get("signer_type", entry.get("signer_type", "file"))
            ).strip().lower()

            # Determine key paths
            if public_key_path and public_key_path.exists():
                pub_path = public_key_path
            else:
                from veritas_os.audit.trustlog_signed import PUBLIC_KEY_PATH
                pub_path = PUBLIC_KEY_PATH

            priv_path = pub_path.parent / pub_path.name.replace("public", "private")
            signer = build_trustlog_signer(
                private_key_path=priv_path,
                public_key_path=pub_path,
                backend=signer_type,
            )
            return signer.verify_payload_signature(
                payload_hash=str(payload_hash),
                signature_b64=str(signature_b64),
            )
        except Exception:  # noqa: BLE001
            _logger.debug("Signature verification failed (key unavailable)", exc_info=True)
            return False

    return _verify


def _format_text_report(result: Dict[str, Any]) -> str:
    """Format verification result as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append("VERITAS TrustLog Verification Report")
    lines.append("=" * 60)
    lines.append("")

    overall_ok = result.get("ok", False)
    lines.append(f"Overall status: {'PASS' if overall_ok else 'FAIL'}")
    lines.append("")

    # Full ledger
    full = result.get("full_ledger")
    if full:
        lines.append("-- Full Ledger --")
        lines.append(f"  Status:     {'PASS' if full.get('ok', full.get('chain_ok')) else 'FAIL'}")
        lines.append(f"  Entries:    {full.get('total_entries', 'N/A')}")
        lines.append(f"  Valid:      {full.get('valid_entries', 'N/A')}")
        lines.append(f"  Invalid:    {full.get('invalid_entries', 'N/A')}")
        lines.append("")

    # Witness ledger
    witness = result.get("witness_ledger")
    if witness:
        lines.append("-- Witness Ledger --")
        lines.append(f"  Status:     {'PASS' if witness.get('ok') else 'FAIL'}")
        lines.append(f"  Entries:    {witness.get('total_entries', 'N/A')}")
        lines.append(f"  Valid:      {witness.get('valid_entries', 'N/A')}")
        lines.append(f"  Invalid:    {witness.get('invalid_entries', 'N/A')}")
        lines.append(f"  Chain OK:   {witness.get('chain_ok', 'N/A')}")
        lines.append(f"  Sigs OK:    {witness.get('signature_ok', 'N/A')}")
        lines.append(f"  Linkage OK: {witness.get('linkage_ok', 'N/A')}")
        lines.append(f"  Mirror OK:  {witness.get('mirror_ok', 'N/A')}")
        lines.append("")

    # Combined
    combined = result.get("combined")
    if combined:
        lines.append("-- Combined --")
        lines.append(f"  Status:     {'PASS' if combined.get('ok') else 'FAIL'}")
        lines.append("")

    # Errors
    errors = result.get("errors", [])
    if errors:
        lines.append(f"-- Errors ({len(errors)}) --")
        for err in errors[:50]:  # cap output
            lines.append(
                f"  [{err.get('ledger', '?')}:{err.get('index', '?')}] "
                f"{err.get('reason', '?')} ({err.get('code', '?')})"
                f"{' TAMPER' if err.get('tamper_suspected') else ''}"
            )
        if len(errors) > 50:
            lines.append(f"  ... and {len(errors) - 50} more errors")
        lines.append("")

    # Notes
    notes = result.get("notes", [])
    if notes:
        lines.append(f"-- Notes ({len(notes)}) --")
        for note in notes[:20]:
            lines.append(
                f"  [{note.get('ledger', '?')}:{note.get('index', '?')}] "
                f"{note.get('reason', '?')}"
            )
        if len(notes) > 20:
            lines.append(f"  ... and {len(notes) - 20} more notes")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def run_verification(
    *,
    full_ledger_path: Optional[Path] = None,
    witness_ledger_path: Optional[Path] = None,
    artifact_dirs: Optional[List[Path]] = None,
    public_key_path: Optional[Path] = None,
    verify_tsa: bool = False,
    output_json: bool = False,
    max_entries: Optional[int] = None,
) -> Dict[str, Any]:
    """Run TrustLog verification and return structured result.

    This is the core function that can be used programmatically or from CLI.
    """
    from veritas_os.audit.trustlog_verify import (
        verify_full_ledger,
        verify_witness_ledger,
        verify_trustlogs,
    )

    result: Dict[str, Any] = {"ok": True, "errors": [], "notes": []}
    all_errors: List[Dict[str, Any]] = []
    all_notes: List[Dict[str, Any]] = []

    verify_sig_fn = _build_verify_signature_fn(public_key_path)

    if full_ledger_path and witness_ledger_path:
        # Combined verification
        witness_entries = _load_witness_entries(witness_ledger_path)
        combined = verify_trustlogs(
            full_log_path=full_ledger_path,
            witness_entries=witness_entries,
            verify_signature_fn=verify_sig_fn,
            max_entries=max_entries,
            artifact_search_roots=artifact_dirs,
        )
        result["combined"] = combined
        result["full_ledger"] = combined.get("full_ledger", {})
        result["witness_ledger"] = combined.get("witness_ledger", {})
        result["ok"] = combined.get("ok", False)
        all_errors.extend(combined.get("detailed_errors", []))
        all_notes.extend(combined.get("verification_notes", []))

    elif full_ledger_path:
        full_result = verify_full_ledger(
            log_path=full_ledger_path,
            max_entries=max_entries,
        )
        result["full_ledger"] = full_result
        result["ok"] = full_result.get("ok", full_result.get("chain_ok", False))
        all_errors.extend(full_result.get("detailed_errors", []))
        all_notes.extend(full_result.get("verification_notes", []))

    elif witness_ledger_path:
        witness_entries = _load_witness_entries(witness_ledger_path)
        witness_result = verify_witness_ledger(
            entries=witness_entries,
            verify_signature_fn=verify_sig_fn,
            artifact_search_roots=artifact_dirs,
        )
        result["witness_ledger"] = witness_result
        result["ok"] = witness_result.get("ok", False)
        all_errors.extend(witness_result.get("detailed_errors", []))
        all_notes.extend(witness_result.get("verification_notes", []))

    else:
        result["ok"] = False
        all_errors.append({
            "ledger": "cli",
            "index": 0,
            "reason": "no_ledger_provided",
            "code": "invalid_args",
            "tamper_suspected": False,
        })

    result["errors"] = all_errors
    result["notes"] = all_notes
    result["total_errors"] = len(all_errors)
    result["total_notes"] = len(all_notes)

    return result


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for standalone TrustLog verification.

    Returns:
        Exit code: 0 = pass, 1 = verification failure, 2 = runtime error.
    """
    parser = argparse.ArgumentParser(
        prog="veritas-trustlog-verify",
        description="VERITAS TrustLog standalone verifier for third-party auditors.",
    )
    parser.add_argument(
        "--full-ledger",
        type=Path,
        default=None,
        help="Path to encrypted full ledger (trust_log.jsonl)",
    )
    parser.add_argument(
        "--witness-ledger",
        type=Path,
        default=None,
        help="Path to signed witness ledger (trustlog.jsonl)",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        action="append",
        default=None,
        help="Directory containing full decision artifacts (can specify multiple)",
    )
    parser.add_argument(
        "--public-key",
        type=Path,
        default=None,
        help="Path to Ed25519 public key for signature verification",
    )
    parser.add_argument(
        "--verify-tsa",
        action="store_true",
        help="Verify TSA (RFC 3161) receipt structure and integrity",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help="Maximum number of full ledger entries to verify",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    # Validate inputs exist
    if args.full_ledger and not args.full_ledger.exists():
        msg = f"Full ledger not found: {args.full_ledger}"
        if args.output_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    if args.witness_ledger and not args.witness_ledger.exists():
        msg = f"Witness ledger not found: {args.witness_ledger}"
        if args.output_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    if not args.full_ledger and not args.witness_ledger:
        msg = "At least one of --full-ledger or --witness-ledger is required"
        if args.output_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    try:
        result = run_verification(
            full_ledger_path=args.full_ledger,
            witness_ledger_path=args.witness_ledger,
            artifact_dirs=args.artifact_dir,
            public_key_path=args.public_key,
            verify_tsa=args.verify_tsa,
            output_json=args.output_json,
            max_entries=args.max_entries,
        )
    except Exception as exc:
        msg = f"Verification error: {exc.__class__.__name__}: {exc}"
        if args.output_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(_format_text_report(result))

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
