"""Pinned production S1 schema validation for NeoMundi RGC v0.1.0."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

SCHEMA_SHA256 = "7a4579e7c526114e08ddab44dd8d9d5b564f60cf68a4928183646480dbc13eb4"
SCHEMA_RESOURCE = "schemas/neomundi-rgc-v01-S1.json"


def validate_neomundi_rgc_v01_s1(artifact: dict[str, Any]) -> None:
    """Reject artifacts that violate the pinned production S1 contract."""
    try:
        raw = files("veritas_os.governance").joinpath(SCHEMA_RESOURCE).read_bytes()
    except (OSError, ModuleNotFoundError) as exc:
        raise ValueError("neomundi_v01_s1_schema_unavailable") from exc

    if hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise ValueError("neomundi_v01_s1_schema_hash_mismatch")

    try:
        schema = json.loads(raw)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(artifact)
    except ValidationError as exc:
        raise ValueError("neomundi_v01_s1_contract_violation") from exc
    except (SchemaError, ValueError, TypeError) as exc:
        raise ValueError("neomundi_v01_s1_schema_invalid") from exc
