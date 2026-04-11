"""Backend-independent TrustLog secure entry construction.

This module extracts the cryptographic pipeline from ``trust_log.py`` so
that **any** storage backend (JSONL, PostgreSQL, …) can reuse the same
sequence without duplicating security-critical logic:

    redact → canonicalize → chain-hash → encrypt → append-ready entry

The pipeline guarantees:
    * PII / secret redaction before hashing.
    * RFC 8785 canonical JSON for deterministic hashing.
    * Hash chain: ``hₜ = SHA256(hₜ₋₁ || rₜ)``.
    * Encryption enforcement (fail-closed when key is missing).

Callers are expected to supply ``previous_hash`` and handle persistence
themselves (file, database, etc.).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from veritas_os.logging.encryption import (
    EncryptionKeyMissing,
    encrypt as _encrypt_line,
    is_encryption_enabled,
)
from veritas_os.logging.redact import redact_entry as _redact_entry
from veritas_os.security.hash import sha256_hex

logger = logging.getLogger(__name__)


# =========================================================================
# Canonical JSON helpers (mirrored from trust_log.py for independence)
# =========================================================================


def _canonical_json(obj: Any) -> bytes:
    """RFC 8785 (JCS) inspired canonical JSON as UTF-8 bytes.

    Guarantees:
        * No whitespace (``separators=(',', ':')``).
        * Keys sorted by Unicode code-point order.
        * Non-serializable values fall back to ``str()``.
    """
    def _default(v: Any) -> Any:
        return str(v)

    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    ).encode("utf-8")


def _normalize_for_hash(entry: Dict[str, Any]) -> str:
    """Return the canonical JSON string used as ``rₜ`` in the chain hash.

    ``sha256`` and ``sha256_prev`` are excluded from the payload before
    serialization so that the hash covers only the record content.
    """
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return _canonical_json(payload).decode("utf-8")


# =========================================================================
# Public API
# =========================================================================


def prepare_entry(
    raw_entry: Dict[str, Any],
    *,
    previous_hash: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """Build an append-ready TrustLog entry **without** persisting it.

    Steps executed (in order):
        1. Copy the entry (caller's dict is never mutated).
        2. Populate ``created_at`` and ``sha256_prev``.
        3. **Redact** PII / secrets.
        4. **Canonicalize** + compute chain hash ``hₜ = SHA256(hₜ₋₁ || rₜ)``.
        5. **Encrypt** the JSON line (fail-closed).

    Args:
        raw_entry: Arbitrary dict to be logged.
        previous_hash: The ``sha256`` of the preceding entry, or ``None``
            for the very first entry in the chain.

    Returns:
        A 2-tuple ``(entry, encrypted_line)`` where:
            * ``entry`` is the redacted dict with ``sha256`` and
              ``sha256_prev`` fields populated.
            * ``encrypted_line`` is the string to be persisted (always
              ``ENC:…`` when encryption is configured).

    Raises:
        EncryptionKeyMissing: When the encryption key is not set.
        TypeError: When the entry cannot be serialized.
        ValueError: When JSON conversion fails.
    """
    entry = dict(raw_entry)
    entry.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    entry["sha256_prev"] = previous_hash

    # Step 1 — Redact
    entry = _redact_entry(entry)

    # Step 2 — Canonicalize + chain hash
    entry_json = _normalize_for_hash(entry)
    combined = (previous_hash + entry_json) if previous_hash else entry_json
    entry["sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    # Step 3 — Encrypt
    line = json.dumps(entry, ensure_ascii=False)
    line = _encrypt_line(line)

    # Step 3.1 — Encryption enforcement (fail-closed)
    if is_encryption_enabled() and not line.startswith("ENC:"):
        raise EncryptionKeyMissing(
            "Plaintext write blocked by policy: encryption is enabled "
            "but _encrypt_line() returned non-encrypted output"
        )

    return entry, line


def compute_sha256(payload: dict) -> str:
    """Compute the SHA-256 hash for an entry payload.

    Thin wrapper around the canonical-JSON + SHA-256 pipeline, exposed
    for callers that need to compute hashes without the full
    ``prepare_entry`` flow (e.g. verification).
    """
    try:
        s = _canonical_json(payload)
    except (TypeError, ValueError):
        logger.debug(
            "compute_sha256: canonical JSON failed, using safe fallback",
            exc_info=True,
        )
        s = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    return sha256_hex(s)
