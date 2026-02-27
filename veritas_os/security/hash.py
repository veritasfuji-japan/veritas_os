"""Hash utilities for canonical JSON payload integrity checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(payload: Any) -> str:
    """Serialize an object into deterministic canonical JSON.

    Args:
        payload: JSON-serializable Python object.

    Returns:
        A compact JSON string with sorted keys and stable separators.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_hex(data: bytes | str) -> str:
    """Compute a SHA-256 hex digest from bytes or a UTF-8 string."""
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_of_canonical_json(payload: Any) -> str:
    """Compute SHA-256 for canonical JSON serialization of ``payload``."""
    return sha256_hex(canonical_json_dumps(payload))
