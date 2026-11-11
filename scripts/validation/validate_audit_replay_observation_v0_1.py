"""Offline format validation for proposed persistent audit observations v0.1.

This module does not open, update, or query any registry. A matching digest
checks self-consistency only; it does not authenticate an origin or authorize
runtime execution. The caller must independently verify #2446 scanner output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from veritas_os.security.hash import sha256_of_canonical_json

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas/veritas_audit_replay_observation_v0_1.schema.json"

_ID_FIELDS = ("packet_id", "case_id", "operation_id", "manifest_id")


def calculate_observation_hash(record: dict[str, Any]) -> str:
    """Return a local deterministic digest, excluding the digest field itself."""
    if not isinstance(record, dict):
        raise TypeError("observation must be a JSON object")
    return sha256_of_canonical_json({
        name: value for name, value in record.items() if name != "record_hash"
    })


def verify_observation_contract(record: Any) -> list[str]:
    """Reject malformed candidate observations; never implies registry storage.

    Results are deterministic error codes. No persistent history, signatures,
    independent timestamps, issuer trust or execution effects are checked.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = [
        "SCHEMA_INVALID"
        for _ in Draft202012Validator(schema).iter_errors(record)
    ]
    if errors:
        return ["SCHEMA_INVALID"]

    # Schema's ASCII-only repository syntax makes casefold deterministic for
    # this proposed namespace, but does NOT authenticate the claimed tenant.
    if record["repository_key"] != record["repository_claim"].lower():
        errors.append("REPOSITORY_NAMESPACE_MISMATCH")
    for name in _ID_FIELDS:
        value = record[name]
        if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            errors.append("INVALID_ID_VALUE")
    if record["record_hash"] != calculate_observation_hash(record):
        errors.append("RECORD_HASH_MISMATCH")
    return sorted(set(errors))
