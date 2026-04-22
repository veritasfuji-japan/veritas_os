# veritas_os/api/routes_governance.py
"""Governance policy API endpoints with RBAC/ABAC support."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated, Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from veritas_os.api.auth import require_permission
from veritas_os.api.rbac import Permission
from veritas_os.api.schemas import (
    GovernanceBindReceiptListResponse,
    GovernanceBindReceiptResponse,
    GovernanceDecisionExportResponse,
    GovernancePolicyBundlePromoteRequest,
    GovernancePolicyBundlePromoteResponse,
    GovernancePolicyResponse,
    GovernancePolicyHistoryResponse,
)
from veritas_os.policy.bind_artifacts import FinalOutcome, find_bind_receipts
from veritas_os.policy.governance_policy_update import update_governance_policy_with_bind_boundary
from veritas_os.policy.policy_bundle_promotion import promote_policy_bundle_with_bind_boundary
from veritas_os.security.hash import sha256_of_canonical_json

# Governance functions accessed via _get_server() for test monkeypatching compat

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


def _resolve_bind_failure_reason(bind_receipt: Dict[str, Any]) -> str | None:
    """Resolve a compact operator-facing bind failure reason from receipt fields."""
    direct_reason = bind_receipt.get("bind_failure_reason")
    if isinstance(direct_reason, str) and direct_reason.strip():
        return direct_reason.strip()
    reason_candidates = (
        bind_receipt.get("rollback_reason"),
        bind_receipt.get("escalation_reason"),
        bind_receipt.get("admissibility_result"),
        bind_receipt.get("risk_check_result"),
        bind_receipt.get("constraint_check_result"),
        bind_receipt.get("authority_check_result"),
        bind_receipt.get("drift_check_result"),
    )
    for candidate in reason_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, dict):
            nested = candidate.get("reason") or candidate.get("message") or candidate.get("detail")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _resolve_bind_reason_code(bind_receipt: Dict[str, Any]) -> str | None:
    """Extract a stable reason code when present in bind receipt check payloads."""
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


def _resolve_policy_bundle_paths(bundle_name: str) -> tuple[Path, Path, Path]:
    """Resolve promotion paths from server config/env with traversal protection."""
    bundles_root = Path(
        (os.getenv("VERITAS_POLICY_BUNDLES_ROOT") or "runtime/policy_bundles").strip()
    ).expanduser().resolve()
    pointer_path = Path(
        (os.getenv("VERITAS_POLICY_ACTIVE_POINTER_PATH") or "runtime/active_bundle.json").strip()
    ).expanduser().resolve()
    target_bundle_dir = (bundles_root / bundle_name).resolve()
    try:
        target_bundle_dir.relative_to(bundles_root)
    except ValueError as exc:
        raise ValueError("invalid_bundle_id") from exc
    return target_bundle_dir, pointer_path, bundles_root


def _bind_response_payload(bind_receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize bind receipt summary payload for governance API responses."""
    return {
        "ok": True,
        "bind_receipt": bind_receipt,
        "bind_outcome": bind_receipt.get("final_outcome"),
        "bind_failure_reason": _resolve_bind_failure_reason(bind_receipt),
        "bind_reason_code": _resolve_bind_reason_code(bind_receipt),
        "bind_receipt_id": bind_receipt.get("bind_receipt_id"),
        "execution_intent_id": bind_receipt.get("execution_intent_id"),
    }


def _governance_decision_hash_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """Return a redacted payload used to compute governance bind decision hash."""
    if not isinstance(body, dict):
        return {}
    payload = dict(body)
    payload.pop("approvals", None)
    approval = payload.get("approval")
    if isinstance(approval, dict):
        payload["approval"] = {
            key: value
            for key, value in approval.items()
            if str(key) not in {"signature", "signatures", "signed_payload"}
        }
    return payload


def _bind_failure_status_and_error(bind_receipt: Dict[str, Any]) -> tuple[int, str]:
    """Map bind outcomes to legacy governance API status/error semantics."""
    outcome = str(bind_receipt.get("final_outcome") or "")
    rollback_reason = str(bind_receipt.get("rollback_reason") or "")
    if outcome == FinalOutcome.PRECONDITION_FAILED.value:
        return 400, "Governance policy validation failed"
    if outcome == FinalOutcome.APPLY_FAILED.value:
        if "GOVERNANCE_POLICY_VALIDATION_FAILED" in rollback_reason:
            return 400, "Governance policy validation failed"
        return 500, "Failed to update governance policy"
    if outcome in {FinalOutcome.BLOCKED.value, FinalOutcome.ESCALATED.value}:
        return 403, "governance approval validation failed"
    return 500, "Failed to update governance policy"


# ------------------------------------------------------------------
# RBAC helpers
# ------------------------------------------------------------------

def _governance_rbac_enabled() -> bool:
    """Return True when governance RBAC/ABAC guard is enabled."""
    return (os.getenv("VERITAS_GOVERNANCE_ENFORCE_RBAC", "1").strip().lower()
            not in {"0", "false", "no", "off"})


def _resolve_governance_allowed_roles() -> set[str]:
    """Resolve allowed governance roles from env or safe defaults."""
    raw = (os.getenv("VERITAS_GOVERNANCE_ALLOWED_ROLES") or "admin,compliance_owner").strip()
    roles = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return roles or {"admin", "compliance_owner"}


def _governance_rbac_bypass_acknowledged() -> bool:
    """Return True only when the operator explicitly acknowledged RBAC bypass."""
    return (os.getenv("VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS", "").strip().lower()
            in {"1", "true", "yes"})


def require_governance_access(
    x_role: Optional[str] = Header(default=None, alias="X-Role"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> bool:
    """Enforce governance RBAC/ABAC constraints for admin endpoints."""
    if not _governance_rbac_enabled():
        if not _governance_rbac_bypass_acknowledged():
            logger.error(
                "SECURITY: governance RBAC disabled without explicit bypass "
                "(set VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS=1 to acknowledge)"
            )
            raise HTTPException(
                status_code=403,
                detail="Governance RBAC is disabled but bypass is not explicitly acknowledged. "
                       "Set VERITAS_GOVERNANCE_ALLOW_RBAC_BYPASS=1 to allow.",
            )
        logger.warning(
            "SECURITY WARNING: governance RBAC/ABAC is disabled by "
            "VERITAS_GOVERNANCE_ENFORCE_RBAC=0 (bypass acknowledged)"
        )
        return True

    role = (x_role or "").strip().lower()
    if role not in _resolve_governance_allowed_roles():
        raise HTTPException(status_code=403, detail="Insufficient governance role")

    expected_tenant = (os.getenv("VERITAS_GOVERNANCE_TENANT_ID") or "").strip()
    if expected_tenant and (x_tenant_id or "").strip() != expected_tenant:
        raise HTTPException(status_code=403, detail="Tenant scope mismatch")

    return True


def _emit_governance_change_alert(previous: Dict[str, Any], updated: Dict[str, Any]) -> None:
    """Emit a realtime alert event when high-impact governance settings change."""
    srv = _get_server()
    critical_keys = ("fuji_rules", "risk_thresholds", "auto_stop")
    changed = [key for key in critical_keys if previous.get(key) != updated.get(key)]
    if not changed:
        return
    srv._publish_event(
        "governance.alert",
        {
            "severity": "high",
            "changed_fields": changed,
            "updated_by": updated.get("updated_by", "api"),
        },
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/v1/governance/value-drift", dependencies=[Depends(require_permission(Permission.governance_read))])
def governance_value_drift(telos_baseline: float = Query(default=0.5, ge=0.0, le=1.0)):
    """Return ValueCore drift metrics against a Telos baseline."""
    srv = _get_server()
    try:
        result = srv.get_value_drift(telos_baseline=telos_baseline)
        return {"ok": True, "value_drift": result}
    except Exception as e:
        logger.error("governance_value_drift failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load value drift metrics"},
        )


@router.get(
    "/v1/governance/policy",
    response_model=GovernancePolicyResponse,
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def governance_get():
    """Return the current governance policy."""
    srv = _get_server()
    try:
        policy = srv.get_policy()
        return {"ok": True, "policy": policy}
    except Exception as e:
        logger.error("governance_get failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load governance policy"},
        )


@router.put(
    "/v1/governance/policy",
    response_model=GovernancePolicyResponse,
    dependencies=[Depends(require_permission(Permission.governance_write))],
)
def governance_put(body: dict):
    """Update the governance policy (partial merge)."""
    srv = _get_server()
    try:
        srv.enforce_four_eyes_approval(body)
        previous = srv.get_policy()
        decision_id = str(body.get("decision_id") or uuid4().hex)
        request_id = str(body.get("request_id") or decision_id)
        policy_snapshot_id = str(previous.get("updated_at") or previous.get("version") or "governance_policy")
        bind_receipt = update_governance_policy_with_bind_boundary(
            decision_id=decision_id,
            request_id=request_id,
            actor_identity=str(body.get("updated_by") or "api"),
            policy_snapshot_id=policy_snapshot_id,
            decision_hash=sha256_of_canonical_json(_governance_decision_hash_payload(body)),
            policy_patch=body,
            policy_reader=srv.get_policy,
            policy_updater=srv.update_policy,
            policy_rollback=getattr(srv, "rollback_policy", None),
            approval_context={"governance_policy_update_approved": True},
            approval_records=body.get("approvals") if isinstance(body.get("approvals"), list) else None,
            policy_lineage=body.get("policy_lineage")
            if isinstance(body.get("policy_lineage"), dict)
            else None,
            governance_policy=previous if isinstance(previous, dict) else None,
            execution_intent_id=str(body.get("execution_intent_id") or "") or None,
            bind_receipt_id=str(body.get("bind_receipt_id") or "") or None,
        ).to_dict()
        updated = srv.get_policy()
        bind_payload = _bind_response_payload(bind_receipt)
        if bind_receipt.get("final_outcome") != FinalOutcome.COMMITTED.value:
            status_code, error_message = _bind_failure_status_and_error(bind_receipt)
            return JSONResponse(
                status_code=status_code,
                content={
                    **bind_payload,
                    "ok": False,
                    "error": error_message,
                    "policy": updated,
                },
            )
        srv._publish_event(
            "governance.updated",
            {"updated_by": updated.get("updated_by", "api")},
        )
        _emit_governance_change_alert(previous=previous, updated=updated)
        return {"ok": True, "policy": updated, **bind_payload}
    except PermissionError as e:
        logger.warning("governance_put rejected: %s", e)
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "governance approval validation failed"},
        )
    except (ValueError, TypeError) as e:
        logger.warning("governance_put validation error: %s", e)
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Governance policy validation failed"},
        )
    except Exception as e:
        logger.error("governance_put failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to update governance policy"},
        )


@router.get(
    "/v1/governance/policy/history",
    response_model=GovernancePolicyHistoryResponse,
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def governance_policy_history(limit: int = Query(default=50, ge=1, le=500)):
    """Return recent governance policy change history (newest first)."""
    srv = _get_server()
    try:
        records = srv.get_policy_history(limit=limit)
        return {"ok": True, "count": len(records), "history": records}
    except Exception as e:
        logger.error("governance_policy_history failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load governance policy history"},
        )


@router.get(
    "/v1/governance/decisions/export",
    response_model=GovernanceDecisionExportResponse,
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def governance_decision_export(
    limit: int = Query(default=100, ge=1, le=1000),
    status: str | None = Query(default=None),
    bind_outcome: Annotated[FinalOutcome | None, Query()] = None,
):
    """Export recent decisions for governance/audit integrations."""
    srv = _get_server()
    try:
        page = srv.get_trust_log_page(cursor=None, limit=limit)
        items = page.get("items", []) if isinstance(page, dict) else []
        normalized: list[dict[str, Any]] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            decision_status = str(entry.get("decision_status") or entry.get("status") or "unknown")
            if status and decision_status != status:
                continue
            decision_id = str(entry.get("decision_id") or entry.get("request_id") or "")
            bind_receipts = find_bind_receipts(decision_id=decision_id) if decision_id else []
            latest_bind = bind_receipts[-1].to_dict() if bind_receipts else {}
            latest_bind_outcome = str(latest_bind.get("final_outcome") or "")
            if bind_outcome and latest_bind_outcome != bind_outcome.value:
                continue
            normalized.append(
                {
                    "request_id": str(entry.get("request_id") or ""),
                    "decision_id": decision_id,
                    "decision_status": decision_status,
                    "risk": entry.get("risk"),
                    "created_at": str(entry.get("created_at") or entry.get("ts") or ""),
                    "approver": str(entry.get("approver") or entry.get("updated_by") or "system"),
                    "trace_sha256": entry.get("sha256"),
                    "bind_outcome": latest_bind_outcome or None,
                    "bind_receipt_id": latest_bind.get("bind_receipt_id"),
                    "execution_intent_id": latest_bind.get("execution_intent_id"),
                    "bind_failure_reason": _resolve_bind_failure_reason(latest_bind),
                    "bind_reason_code": _resolve_bind_reason_code(latest_bind),
                    "authority_check_result": latest_bind.get("authority_check_result"),
                    "constraint_check_result": latest_bind.get("constraint_check_result"),
                    "drift_check_result": latest_bind.get("drift_check_result"),
                    "risk_check_result": latest_bind.get("risk_check_result"),
                }
            )
        return {"ok": True, "count": len(normalized), "items": normalized}
    except Exception as e:
        logger.error("governance_decision_export failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to export governance decisions"},
        )


@router.get(
    "/v1/governance/bind-receipts",
    response_model=GovernanceBindReceiptListResponse,
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def governance_bind_receipts(
    decision_id: str | None = Query(default=None),
    execution_intent_id: str | None = Query(default=None),
):
    """Return bind receipt artifacts filtered by decision/execution intent lineage."""
    try:
        receipts = find_bind_receipts(
            decision_id=decision_id,
            execution_intent_id=execution_intent_id,
        )
        return {
            "ok": True,
            "count": len(receipts),
            "items": [receipt.to_dict() for receipt in receipts],
        }
    except Exception as e:
        logger.error("governance_bind_receipts failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load bind receipts"},
        )


@router.get(
    "/v1/governance/bind-receipts/{bind_receipt_id}",
    response_model=GovernanceBindReceiptResponse,
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def governance_bind_receipt(bind_receipt_id: str):
    """Return a bind receipt artifact by ``bind_receipt_id``."""
    try:
        receipts = find_bind_receipts(bind_receipt_id=bind_receipt_id)
        if not receipts:
            return JSONResponse(status_code=404, content={"ok": False, "error": "bind_receipt_not_found"})
        receipt = receipts[-1].to_dict()
        return {
            "ok": True,
            "bind_receipt": receipt,
            "bind_outcome": receipt.get("final_outcome"),
            "bind_failure_reason": _resolve_bind_failure_reason(receipt),
            "bind_reason_code": _resolve_bind_reason_code(receipt),
            "bind_receipt_id": receipt.get("bind_receipt_id"),
            "execution_intent_id": receipt.get("execution_intent_id"),
            "authority_check_result": receipt.get("authority_check_result"),
            "constraint_check_result": receipt.get("constraint_check_result"),
            "drift_check_result": receipt.get("drift_check_result"),
            "risk_check_result": receipt.get("risk_check_result"),
        }
    except Exception as e:
        logger.error("governance_bind_receipt failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load bind receipt"},
        )


@router.post(
    "/v1/governance/policy-bundles/promote",
    response_model=GovernancePolicyBundlePromoteResponse,
    dependencies=[Depends(require_permission(Permission.governance_write))],
)
def governance_promote_policy_bundle(
    body: GovernancePolicyBundlePromoteRequest,
    x_role: Optional[str] = Header(default=None, alias="X-Role"),
):
    """Promote policy bundle pointer via existing bind-boundary adapter path."""
    bundle_name = (body.bundle_id or body.bundle_dir_name or "").strip()
    actor_identity = (x_role or "").strip() or "governance_api"
    try:
        target_bundle_dir, pointer_path, bundles_root = _resolve_policy_bundle_paths(bundle_name)
    except ValueError:
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_bundle_id"})

    try:
        current_policy = _get_server().get_policy()
        receipt = promote_policy_bundle_with_bind_boundary(
            decision_id=body.decision_id,
            request_id=body.request_id,
            actor_identity=actor_identity,
            policy_snapshot_id=body.policy_snapshot_id,
            decision_hash=body.decision_hash,
            target_bundle_dir=target_bundle_dir,
            pointer_path=pointer_path,
            allowed_root=bundles_root,
            approval_context=dict(body.approval_context or {}),
            governance_policy=current_policy if isinstance(current_policy, dict) else None,
        )
        return _bind_response_payload(receipt.to_dict())
    except (ValueError, TypeError) as exc:
        logger.warning("governance_promote_policy_bundle validation error: %s", exc)
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_promotion_request"})
    except Exception as exc:
        logger.error("governance_promote_policy_bundle failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to promote policy bundle"},
        )
