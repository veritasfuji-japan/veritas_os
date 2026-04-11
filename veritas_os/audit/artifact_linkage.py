"""Artifact linkage verification helpers for signed TrustLog witness entries.

This module resolves the canonical *full payload* artifact referenced by
witness entries and verifies that its recomputed hash matches
``full_payload_hash``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from veritas_os.logging.encryption import (
    DecryptionError,
    EncryptionKeyMissing,
    decrypt,
)
from veritas_os.logging.paths import LOG_DIR
from veritas_os.security.hash import sha256_of_canonical_json

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


@dataclass(frozen=True)
class ArtifactReference:
    """Structured artifact reference carried by witness entries."""

    artifact_ref: str
    artifact_type: str
    artifact_storage_backend: str
    artifact_locator: str
    artifact_hash_algorithm: str


@dataclass(frozen=True)
class ArtifactLinkageResult:
    """Result of cross-verifying witness linkage against stored artifacts."""

    ok: bool
    reason: Optional[str] = None


def _iter_roots(extra_roots: Optional[Sequence[Path]]) -> Iterable[Path]:
    roots: List[Path] = [LOG_DIR]
    if extra_roots:
        roots.extend(extra_roots)
    seen: set[Path] = set()
    for root in roots:
        resolved = Path(root).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _parse_artifact_reference(raw: Any) -> Optional[ArtifactReference]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("malformed_artifact_ref")

    required_keys = (
        "artifact_ref",
        "artifact_type",
        "artifact_storage_backend",
        "artifact_locator",
        "artifact_hash_algorithm",
    )
    values: Dict[str, str] = {}
    for key in required_keys:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("malformed_artifact_ref")
        values[key] = value.strip()

    if values["artifact_hash_algorithm"] != "sha256_canonical_json":
        raise ValueError("malformed_artifact_ref")

    return ArtifactReference(**values)


def _iter_full_ledger_entries(log_path: Path) -> Iterable[Dict[str, Any]]:
    if not log_path.exists() or not log_path.is_file():
        return
    with log_path.open("r", encoding="utf-8") as file:
        for raw in file:
            line = raw.strip()
            if not line:
                continue
            try:
                decoded = decrypt(line)
                entry = json.loads(decoded)
            except (json.JSONDecodeError, ValueError, EncryptionKeyMissing, DecryptionError):
                continue
            if isinstance(entry, dict):
                yield entry


def _load_json_entry(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_via_full_ledger(
    *,
    sha256_value: Optional[str],
    request_id: Optional[str],
    roots: Sequence[Path],
) -> Optional[Dict[str, Any]]:
    for root in roots:
        log_path = root / "trust_log.jsonl"
        for payload in _iter_full_ledger_entries(log_path):
            if sha256_value and payload.get("sha256") == sha256_value:
                return payload
            if request_id and payload.get("request_id") == request_id:
                return payload
    return None


def _resolve_via_decide_files(request_id: Optional[str], roots: Sequence[Path]) -> Optional[Dict[str, Any]]:
    if not request_id:
        return None

    for root in roots:
        for file_path in sorted(root.glob("decide_*.json"), reverse=True):
            payload = _load_json_entry(file_path)
            if payload is None:
                continue
            if payload.get("request_id") == request_id:
                return payload
    return None


def _resolve_payload_for_entry(
    entry: Dict[str, Any],
    *,
    roots: Sequence[Path],
) -> Optional[Dict[str, Any]]:
    decision_payload = entry.get("decision_payload")
    request_id = decision_payload.get("request_id") if isinstance(decision_payload, dict) else None

    artifact_ref = _parse_artifact_reference(entry.get("artifact_ref"))
    if artifact_ref is not None:
        backend = artifact_ref.artifact_storage_backend
        locator = artifact_ref.artifact_locator

        if backend == "trustlog_full_ledger":
            if locator.startswith("sha256:"):
                digest = locator.split(":", 1)[1].strip()
                if not _SHA256_HEX_RE.fullmatch(digest):
                    raise ValueError("malformed_artifact_ref")
                payload = _resolve_via_full_ledger(
                    sha256_value=digest,
                    request_id=None,
                    roots=roots,
                )
            elif locator.startswith("request_id:"):
                payload = _resolve_via_full_ledger(
                    sha256_value=None,
                    request_id=locator.split(":", 1)[1].strip(),
                    roots=roots,
                )
            else:
                raise ValueError("malformed_artifact_ref")
            if payload is None:
                return None
            return payload

        if backend == "local_json_file":
            file_path = Path(locator)
            if not file_path.is_absolute() and roots:
                file_path = roots[0] / file_path
            payload = _load_json_entry(file_path)
            if payload is None:
                if file_path.exists():
                    raise PermissionError("artifact_unreadable")
                return None
            return payload

        raise ValueError("unsupported_artifact_backend")

    # Legacy fallback: recover from full ledger by sha256/request_id, then decide files.
    payload = _resolve_via_full_ledger(
        sha256_value=str(entry.get("full_payload_sha256") or "").strip() or None,
        request_id=str(request_id).strip() if isinstance(request_id, str) else None,
        roots=roots,
    )
    if payload is not None:
        return payload

    payload = _resolve_via_decide_files(
        request_id=str(request_id).strip() if isinstance(request_id, str) else None,
        roots=roots,
    )
    if payload is not None:
        return payload

    return None


def verify_entry_artifact_linkage(
    entry: Dict[str, Any],
    *,
    search_roots: Optional[Sequence[Path]] = None,
) -> ArtifactLinkageResult:
    """Verify witness ``full_payload_hash`` against resolved full artifact.

    Returns legacy-compatible success when ``full_payload_hash`` is absent.
    """
    expected_hash = entry.get("full_payload_hash")
    if expected_hash is None:
        return ArtifactLinkageResult(ok=True)
    if not isinstance(expected_hash, str) or not _SHA256_HEX_RE.fullmatch(expected_hash):
        return ArtifactLinkageResult(ok=False, reason="full_payload_hash_invalid")

    roots = list(_iter_roots(search_roots))

    try:
        payload = _resolve_payload_for_entry(entry, roots=roots)
    except PermissionError:
        return ArtifactLinkageResult(ok=False, reason="artifact_unreadable")
    except ValueError as exc:
        return ArtifactLinkageResult(ok=False, reason=str(exc))

    if payload is None:
        # Legacy-compatible mode: if no structured artifact_ref is present and
        # no local source artifact can be resolved, keep prior behavior.
        if entry.get("artifact_ref") is None:
            return ArtifactLinkageResult(ok=True)
        return ArtifactLinkageResult(ok=False, reason="artifact_missing")

    try:
        recomputed = sha256_of_canonical_json(payload)
    except (TypeError, ValueError):
        return ArtifactLinkageResult(ok=False, reason="canonicalization_failed")

    if recomputed != expected_hash:
        return ArtifactLinkageResult(ok=False, reason="linkage_hash_mismatch")

    return ArtifactLinkageResult(ok=True)
