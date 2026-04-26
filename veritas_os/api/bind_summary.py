"""Shared bind summary vocabulary and serializers for API responses."""
from __future__ import annotations

from typing import Any

from veritas_os.api.bind_target_catalog import resolve_bind_target_metadata


def resolve_bind_failure_reason(bind_receipt: dict[str, Any]) -> str | None:
    """Resolve compact operator-facing bind failure reason from receipt fields."""
    direct_reason = bind_receipt.get("bind_failure_reason")
    if isinstance(direct_reason, str) and direct_reason.strip():
        return direct_reason.strip()
    for key in (
        "rollback_reason",
        "escalation_reason",
        "admissibility_result",
        "risk_check_result",
        "constraint_check_result",
        "authority_check_result",
        "drift_check_result",
    ):
        candidate = bind_receipt.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, dict):
            nested = candidate.get("reason") or candidate.get("message") or candidate.get("detail")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def resolve_bind_reason_code(bind_receipt: dict[str, Any]) -> str | None:
    """Extract a stable bind reason code from the receipt payload."""
    direct_reason_code = bind_receipt.get("bind_reason_code")
    if isinstance(direct_reason_code, str) and direct_reason_code.strip():
        return direct_reason_code.strip()
    for key in (
        "admissibility_result",
        "risk_check_result",
        "constraint_check_result",
        "authority_check_result",
        "drift_check_result",
    ):
        value = bind_receipt.get(key)
        if not isinstance(value, dict):
            continue
        raw = value.get("reason_code") or value.get("code")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def enrich_bind_receipt_payload(bind_receipt: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical bind target metadata to any bind receipt payload."""
    target_metadata = resolve_bind_target_metadata(
        bind_receipt.get("target_path"),
        bind_receipt.get("target_type"),
    )
    return {
        **bind_receipt,
        "target_path_type": target_metadata["target_path_type"],
        "target_label": target_metadata["label"],
        "operator_surface": target_metadata["operator_surface"],
        "relevant_ui_href": target_metadata["relevant_ui_href"],
    }


def build_bind_summary_from_receipt(bind_receipt: dict[str, Any]) -> dict[str, Any]:
    """Build shared compact bind summary from a bind receipt payload."""
    enriched_receipt = enrich_bind_receipt_payload(bind_receipt)
    failed_predicates = enriched_receipt.get("failed_predicates")
    stale_predicates = enriched_receipt.get("stale_predicates")
    missing_predicates = enriched_receipt.get("missing_predicates")
    return {
        "bind_outcome": enriched_receipt.get("final_outcome"),
        "bind_failure_reason": resolve_bind_failure_reason(enriched_receipt),
        "bind_reason_code": resolve_bind_reason_code(enriched_receipt),
        "bind_receipt_id": enriched_receipt.get("bind_receipt_id"),
        "execution_intent_id": enriched_receipt.get("execution_intent_id"),
        "authority_check_result": enriched_receipt.get("authority_check_result"),
        "constraint_check_result": enriched_receipt.get("constraint_check_result"),
        "drift_check_result": enriched_receipt.get("drift_check_result"),
        "risk_check_result": enriched_receipt.get("risk_check_result"),
        "target_path": enriched_receipt.get("target_path"),
        "target_type": enriched_receipt.get("target_type"),
        "target_path_type": enriched_receipt.get("target_path_type"),
        "target_label": enriched_receipt.get("target_label"),
        "operator_surface": enriched_receipt.get("operator_surface"),
        "relevant_ui_href": enriched_receipt.get("relevant_ui_href"),
        "action_contract_id": enriched_receipt.get("action_contract_id"),
        "authority_evidence_id": enriched_receipt.get("authority_evidence_id"),
        "authority_validation_status": enriched_receipt.get("authority_validation_status"),
        "commit_boundary_result": enriched_receipt.get("commit_boundary_result"),
        "failed_predicate_count": len(failed_predicates) if isinstance(failed_predicates, list) else None,
        "stale_predicate_count": len(stale_predicates) if isinstance(stale_predicates, list) else None,
        "missing_predicate_count": (
            len(missing_predicates) if isinstance(missing_predicates, list) else None
        ),
        "refusal_basis": enriched_receipt.get("refusal_basis"),
        "escalation_basis": enriched_receipt.get("escalation_basis"),
        "irreversibility_boundary_id": enriched_receipt.get("irreversibility_boundary_id"),
    }


def build_target_metadata(bind_receipt: dict[str, Any]) -> dict[str, Any]:
    """Build target metadata compatibility payload from enriched bind receipt."""
    enriched_receipt = enrich_bind_receipt_payload(bind_receipt)
    return {
        "target_path": enriched_receipt.get("target_path"),
        "target_type": enriched_receipt.get("target_type"),
        "target_path_type": enriched_receipt.get("target_path_type"),
        "label": enriched_receipt.get("target_label"),
        "operator_surface": enriched_receipt.get("operator_surface"),
        "relevant_ui_href": enriched_receipt.get("relevant_ui_href"),
    }


def build_bind_response_payload(bind_receipt: dict[str, Any]) -> dict[str, Any]:
    """Build compatibility bind payload + shared bind_summary from receipt."""
    enriched_receipt = enrich_bind_receipt_payload(bind_receipt)
    bind_summary = build_bind_summary_from_receipt(enriched_receipt)
    return {
        "bind_receipt": enriched_receipt,
        "bind_summary": bind_summary,
        **{key: bind_summary.get(key) for key in (
            "bind_outcome",
            "bind_failure_reason",
            "bind_reason_code",
            "bind_receipt_id",
            "execution_intent_id",
            "authority_check_result",
            "constraint_check_result",
            "drift_check_result",
            "risk_check_result",
        )},
        "target_metadata": build_target_metadata(enriched_receipt),
    }
