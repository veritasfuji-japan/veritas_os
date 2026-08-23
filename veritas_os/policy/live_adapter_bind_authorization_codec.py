"""Canonical encoding and signature payloads for Real Bind Authorization v1."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    AUTHORIZATION_SIGNATURE_DOMAIN, AUTHORIZER_SIGNATURE_DOMAIN, DOMAINS,
    LiveAdapterBindAuthorizationError,
)
from veritas_os.security.hash import canonical_json_dumps

def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise LiveAdapterBindAuthorizationError("LABA_INVALID_VALUE")


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterBindAuthorizationError("LABA_TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc).isoformat()


def _digest(domain: str, value: Any) -> str:
    payload = json.dumps(
        {"domain": domain, "value": _json(value)},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _artifact_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_bind_authorization_id",
        "live_adapter_bind_authorization_hash",
        "authorization_signature",
    }
    return _digest(
        DOMAINS["artifact"],
        {key: value for key, value in raw.items() if key not in omitted},
    )


def bind_authorizer_decision_signature_payload(artifact: dict[str, Any]) -> str:
    """Canonical domain-separated authorizer decision signature payload."""
    return canonical_json_dumps(
        {
            "domain": AUTHORIZER_SIGNATURE_DOMAIN,
            "artifact_type": artifact.get("artifact_type"),
            "artifact_version": artifact.get("artifact_version"),
            "decision_hash": artifact.get("decision_hash"),
            "decision": artifact.get("decision"),
            "signer": artifact.get("signer"),
            "signed_at": artifact.get("signed_at"),
        }
    )


def bind_authorization_artifact_signature_payload(artifact: dict[str, Any]) -> str:
    """Canonical domain-separated final authorization signature payload."""
    unsigned = {
        key: value
        for key, value in artifact.items()
        if key != "authorization_signature"
    }
    return canonical_json_dumps(
        {"domain": AUTHORIZATION_SIGNATURE_DOMAIN, "artifact": unsigned}
    )
