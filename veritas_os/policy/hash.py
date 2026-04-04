"""Semantic hashing based on canonical policy IR."""

from __future__ import annotations

import hashlib
import json

from .ir import CanonicalPolicyIR


def canonical_ir_json(canonical_ir: CanonicalPolicyIR) -> str:
    """Serialize canonical IR into stable JSON bytes representation."""
    return json.dumps(
        canonical_ir,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def semantic_policy_hash(canonical_ir: CanonicalPolicyIR) -> str:
    """Compute SHA-256 semantic hash from canonical policy IR.

    Raises :class:`ValueError` when *canonical_ir* is not a mapping or is
    missing the ``policy_id`` key required by the canonical schema.
    """
    if not isinstance(canonical_ir, dict):
        raise ValueError(
            f"canonical_ir must be a dict, got {type(canonical_ir).__name__}"
        )
    if "policy_id" not in canonical_ir:
        raise ValueError("canonical_ir missing required key 'policy_id'")
    payload = canonical_ir_json(canonical_ir).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
