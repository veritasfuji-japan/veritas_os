"""Canonical replay semantic profile shared by reports and evidence."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

SEMANTIC_PROFILE = "veritas.replay-semantic/v1"


def strict_canonical_json(value: Any) -> str:
    """Serialize exact JSON values, rejecting ambiguous Python values."""
    _validate_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_json(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            _validate_json(item)
        return
    raise TypeError("unsupported canonical JSON value")


def semantic_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Project the stable replay fields used by all v1 comparisons."""
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    fuji = payload.get("fuji") if isinstance(payload.get("fuji"), dict) else {}
    extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        evidence = extras.get("evidence") if isinstance(extras.get("evidence"), list) else []
    stable_evidence = []
    for item in evidence:
        if isinstance(item, dict):
            stable_evidence.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "url": item.get("url") or item.get("uri"),
                    "source": item.get("source"),
                    "snippet": item.get("snippet"),
                }
            )
    stable_evidence.sort(
        key=lambda item: str(
            item.get("id")
            or item.get("title")
            or item.get("url")
            or item.get("source")
            or ""
        ).lower()
    )
    projection: dict[str, Any] = {
        "decision": {
            "output": decision.get("output"),
            "answer": decision.get("answer"),
        },
        "fuji": {"result": fuji.get("result"), "status": fuji.get("status")},
        "value_scores": payload.get("value_scores"),
        "evidence": stable_evidence,
    }
    continuation = payload.get("continuation")
    if isinstance(continuation, dict):
        state = continuation.get("state") if isinstance(continuation.get("state"), dict) else {}
        receipt = continuation.get("receipt") if isinstance(continuation.get("receipt"), dict) else {}
        projection["continuation_state"] = {
            "claim_lineage_id": state.get("claim_lineage_id"),
            "claim_status": state.get("claim_status"),
            "law_version": state.get("law_version"),
            "snapshot_id": state.get("snapshot_id"),
        }
        projection["continuation_receipt"] = {
            "receipt_id": receipt.get("receipt_id"),
            "revalidation_status": receipt.get("revalidation_status"),
            "revalidation_outcome": receipt.get("revalidation_outcome"),
            "divergence_flag": receipt.get("divergence_flag"),
            "should_refuse_before_effect": receipt.get(
                "should_refuse_before_effect"
            ),
            "reason_codes": receipt.get("revalidation_reason_codes"),
        }
    _validate_json(projection)
    return projection


def semantic_hash(projection: dict[str, Any]) -> str:
    """Hash a semantic projection with explicit profile domain separation."""
    preimage = {"profile": SEMANTIC_PROFILE, "projection": projection}
    return hashlib.sha256(strict_canonical_json(preimage).encode("utf-8")).hexdigest()
