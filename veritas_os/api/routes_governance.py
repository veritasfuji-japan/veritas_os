# veritas_os/api/routes_governance.py
"""Governance policy API endpoints with RBAC/ABAC support."""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from veritas_os.api.auth import require_permission
from veritas_os.api.bind_summary import (
    build_bind_response_payload,
    build_bind_summary_from_receipt,
    enrich_bind_receipt_payload,
    resolve_bind_reason_code,
)
from veritas_os.api.bind_target_catalog import get_target_catalog_payload
from veritas_os.api.rbac import Permission
from veritas_os.api.governance_live_snapshot import build_governance_live_snapshot
from veritas_os.api.schemas import (
    GovernanceBindReceiptExportResponse,
    GovernanceBindReceiptListResponse,
    GovernanceBindReceiptResponse,
    GovernanceDecisionExportResponse,
    GovernancePolicyBundlePromoteRequest,
    GovernancePolicyBundlePromoteResponse,
    GovernancePolicyResponse,
    GovernancePolicyHistoryResponse,
)
from veritas_os.policy.bind_route_markers import requires_bind_boundary
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome, find_bind_receipts
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


class BindReceiptListSort(str):
    """Canonical sort keys for bind receipt list endpoint."""

    NEWEST = "newest"
    OLDEST = "oldest"


def _parse_bool_query(value: str | None, *, field_name: str) -> bool | None:
    """Parse an optional query boolean with stable 400 semantics."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid_{field_name}")


def _parse_bind_receipt_sort(value: str | None) -> str:
    """Resolve bind receipt list sort key with stable 400 semantics."""
    if value is None:
        return BindReceiptListSort.NEWEST
    normalized = value.strip().lower()
    if normalized not in {BindReceiptListSort.NEWEST, BindReceiptListSort.OLDEST}:
        raise ValueError("invalid_sort")
    return normalized


def _parse_bind_receipt_outcome(value: str | None) -> str | None:
    """Normalize bind outcome query for list endpoint filtering."""
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    valid = {item.value for item in FinalOutcome}
    if normalized not in valid:
        raise ValueError("invalid_outcome")
    return normalized


def _parse_bind_receipt_timestamp(bind_receipt: dict[str, Any]) -> datetime | None:
    """Parse bind receipt timestamp from known fields as UTC datetime."""
    for key in ("occurred_at", "created_at", "bind_ts"):
        raw = bind_receipt.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _canonical_path(value: Any) -> str:
    """Normalize API path-like value for canonical matching."""
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if not stripped:
        return ""
    return stripped.rstrip("/") or "/"


def _receipt_matches_lineage_query(bind_receipt: dict[str, Any], lineage_query: str) -> bool:
    """Return True when lineage query matches common bind lineage identifiers."""
    query = lineage_query.strip().lower()
    if not query:
        return True
    for key in ("decision_id", "execution_intent_id", "bind_receipt_id", "policy_snapshot_id"):
        value = bind_receipt.get(key)
        if isinstance(value, str) and query in value.lower():
            return True
    return False


def _apply_bind_receipt_filters(
    receipts: list[BindReceipt],
    *,
    target_path: str | None,
    target_type: str | None,
    outcome: str | None,
    reason_code: str | None,
    lineage_query: str | None,
    failed_only: bool | None,
    recent_only: bool | None,
    sort: str,
) -> list[dict[str, Any]]:
    """Apply additive bind receipt list query semantics deterministically."""
    now_utc = datetime.now(timezone.utc)
    recent_threshold = now_utc - timedelta(hours=24)
    canonical_target_path = _canonical_path(target_path) if target_path else None
    reason_query = (reason_code or "").strip().lower()
    lineage_term = (lineage_query or "").strip()

    filtered: list[dict[str, Any]] = []
    for receipt in receipts:
        payload = receipt.to_dict()

        if canonical_target_path:
            payload_target_path = _canonical_path(payload.get("target_path"))
            if payload_target_path != canonical_target_path:
                continue
        if target_type and payload.get("target_type") != target_type:
            continue
        if outcome and str(payload.get("final_outcome") or "").upper() != outcome:
            continue

        resolved_reason_code = (resolve_bind_reason_code(payload) or "").lower()
        if reason_query and reason_query not in resolved_reason_code:
            continue

        if lineage_term and not _receipt_matches_lineage_query(payload, lineage_term):
            continue

        normalized_outcome = str(payload.get("final_outcome") or "").upper()
        if failed_only is True and normalized_outcome == FinalOutcome.COMMITTED.value:
            continue

        if recent_only is True:
            parsed_ts = _parse_bind_receipt_timestamp(payload)
            if parsed_ts is None or parsed_ts < recent_threshold:
                continue

        filtered.append(payload)

    filtered.sort(
        key=_bind_receipt_cursor_key,
        reverse=sort == BindReceiptListSort.NEWEST,
    )
    return filtered



def _bind_receipt_cursor_key(bind_receipt: dict[str, Any]) -> tuple[datetime, str]:
    """Return deterministic cursor key tuple for bind receipt pagination."""
    return (
        _parse_bind_receipt_timestamp(bind_receipt) or datetime.min.replace(tzinfo=timezone.utc),
        str(bind_receipt.get("bind_receipt_id") or ""),
    )


def _encode_bind_receipt_cursor(*, sort: str, bind_receipt: dict[str, Any]) -> str:
    """Encode opaque cursor payload for bind receipt pagination windowing."""
    timestamp, bind_receipt_id = _bind_receipt_cursor_key(bind_receipt)
    payload = {
        "s": sort,
        "t": timestamp.isoformat(),
        "id": bind_receipt_id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


def _decode_bind_receipt_cursor(cursor: str, *, expected_sort: str) -> tuple[datetime, str]:
    """Decode and validate bind receipt cursor payload for stable paging."""
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc

    if not isinstance(payload, dict):
        raise ValueError("invalid_cursor")
    if payload.get("s") != expected_sort:
        raise ValueError("invalid_cursor")

    raw_timestamp = payload.get("t")
    raw_bind_receipt_id = payload.get("id")
    if not isinstance(raw_timestamp, str) or not isinstance(raw_bind_receipt_id, str):
        raise ValueError("invalid_cursor")

    try:
        timestamp = datetime.fromisoformat(raw_timestamp)
    except ValueError as exc:
        raise ValueError("invalid_cursor") from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc), raw_bind_receipt_id


def _paginate_bind_receipt_items(
    *,
    items: list[dict[str, Any]],
    sort: str,
    limit: int | None,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Return paged bind receipt items with has_more and next_cursor."""
    start_index = 0
    if cursor:
        cursor_key = _decode_bind_receipt_cursor(cursor, expected_sort=sort)
        for idx, item in enumerate(items):
            if _bind_receipt_cursor_key(item) == cursor_key:
                start_index = idx + 1
                break
        else:
            raise ValueError("invalid_cursor")

    if limit is None:
        page_items = items[start_index:]
        return page_items, False, None

    page_items = items[start_index:start_index + limit]
    has_more = (start_index + limit) < len(items)
    next_cursor = _encode_bind_receipt_cursor(sort=sort, bind_receipt=page_items[-1]) if has_more and page_items else None
    return page_items, has_more, next_cursor


def _bind_receipt_applied_filters(
    *,
    decision_id: str | None,
    execution_intent_id: str | None,
    target_path: str | None,
    target_type: str | None,
    outcome: str | None,
    reason_code: str | None,
    lineage_query: str | None,
    failed_only: bool | None,
    recent_only: bool | None,
) -> dict[str, Any]:
    """Build operator-visible summary of applied bind receipt filters."""
    return {
        "decision_id": decision_id,
        "execution_intent_id": execution_intent_id,
        "target_path": target_path,
        "target_type": target_type,
        "outcome": outcome,
        "reason_code": reason_code,
        "lineage_query": lineage_query,
        "failed_only": failed_only,
        "recent_only": recent_only,
    }


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
@requires_bind_boundary(
    target_path="/v1/governance/policy",
    target_type="governance_policy",
    target_path_type="governance_policy_update",
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
        bind_payload = build_bind_response_payload(bind_receipt)
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
            latest_bind = enrich_bind_receipt_payload(bind_receipts[-1].to_dict()) if bind_receipts else {}
            latest_bind_outcome = str(latest_bind.get("final_outcome") or "")
            if bind_outcome and latest_bind_outcome != bind_outcome.value:
                continue
            bind_summary = build_bind_summary_from_receipt(latest_bind) if latest_bind else None
            normalized.append(
                {
                    "request_id": str(entry.get("request_id") or ""),
                    "decision_id": decision_id,
                    "decision_status": decision_status,
                    "risk": entry.get("risk"),
                    "created_at": str(entry.get("created_at") or entry.get("ts") or ""),
                    "approver": str(entry.get("approver") or entry.get("updated_by") or "system"),
                    "trace_sha256": entry.get("sha256"),
                    "bind_summary": bind_summary,
                    "bind_outcome": (bind_summary or {}).get("bind_outcome") or latest_bind_outcome or None,
                    "bind_receipt_id": (bind_summary or {}).get("bind_receipt_id"),
                    "execution_intent_id": (bind_summary or {}).get("execution_intent_id"),
                    "bind_failure_reason": (bind_summary or {}).get("bind_failure_reason"),
                    "bind_reason_code": (bind_summary or {}).get("bind_reason_code"),
                    "authority_check_result": (bind_summary or {}).get("authority_check_result"),
                    "constraint_check_result": (bind_summary or {}).get("constraint_check_result"),
                    "drift_check_result": (bind_summary or {}).get("drift_check_result"),
                    "risk_check_result": (bind_summary or {}).get("risk_check_result"),
                    "target_path_type": (bind_summary or {}).get("target_path_type"),
                    "target_label": (bind_summary or {}).get("target_label"),
                    "operator_surface": (bind_summary or {}).get("operator_surface"),
                    "relevant_ui_href": (bind_summary or {}).get("relevant_ui_href"),
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
    decision_id: str | None = Query(default=None, description="Filter by exact governance decision_id."),
    execution_intent_id: str | None = Query(default=None, description="Filter by exact execution_intent_id."),
    target_path: str | None = Query(default=None, description="Filter by canonical target_path match."),
    target_type: str | None = Query(default=None, description="Filter by exact target_type match."),
    outcome: str | None = Query(default=None, description="Filter by final_outcome enum value."),
    reason_code: str | None = Query(default=None, description="Case-insensitive contains match for bind reason_code."),
    lineage_query: str | None = Query(
        default=None,
        description="Case-insensitive contains search across decision_id, execution_intent_id, bind_receipt_id, and policy_snapshot_id.",
    ),
    failed_only: str | None = Query(
        default=None,
        description="When true, include outcomes except COMMITTED.",
    ),
    recent_only: str | None = Query(
        default=None,
        description="When true, include only receipts from the last 24 hours based on server clock.",
    ),
    limit: int | None = Query(default=None, ge=1, le=200, description="Max receipts returned (safe upper bound: 200)."),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor for continuing list results."),
    sort: str | None = Query(default=None, description="Sort order: newest (default) or oldest."),
):
    """Return bind receipt artifacts with additive operator-focused server-side filtering."""
    try:
        parsed_outcome = _parse_bind_receipt_outcome(outcome)
        parsed_sort = _parse_bind_receipt_sort(sort)
        parsed_failed_only = _parse_bool_query(failed_only, field_name="failed_only")
        parsed_recent_only = _parse_bool_query(recent_only, field_name="recent_only")
    except ValueError as exc:
        detail = "invalid_cursor" if str(exc) == "invalid_cursor" else "invalid_query_parameter"
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "invalid_bind_receipt_query",
                "detail": detail,
            },
        )

    try:
        receipts = find_bind_receipts(
            decision_id=decision_id,
            execution_intent_id=execution_intent_id,
        )
        filtered_items = _apply_bind_receipt_filters(
            receipts,
            target_path=target_path,
            target_type=target_type,
            outcome=parsed_outcome,
            reason_code=reason_code,
            lineage_query=lineage_query,
            failed_only=parsed_failed_only,
            recent_only=parsed_recent_only,
            sort=parsed_sort,
        )
        enriched_items = [enrich_bind_receipt_payload(item) for item in filtered_items]
        page_items, has_more, next_cursor = _paginate_bind_receipt_items(
            items=enriched_items,
            sort=parsed_sort,
            limit=limit,
            cursor=cursor,
        )
        applied_filters = _bind_receipt_applied_filters(
            decision_id=decision_id,
            execution_intent_id=execution_intent_id,
            target_path=target_path,
            target_type=target_type,
            outcome=parsed_outcome,
            reason_code=reason_code,
            lineage_query=lineage_query,
            failed_only=parsed_failed_only,
            recent_only=parsed_recent_only,
        )
        return {
            "ok": True,
            "count": len(page_items),
            "returned_count": len(page_items),
            "items": page_items,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "sort": parsed_sort,
            "limit": limit,
            "applied_filters": applied_filters,
            "total_count": len(filtered_items),
            "target_catalog": get_target_catalog_payload(),
        }
    except ValueError as exc:
        if str(exc) == "invalid_cursor":
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_bind_receipt_query", "detail": "invalid_cursor"},
            )
        raise
    except Exception as e:
        logger.error("governance_bind_receipts failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load bind receipts"},
        )




@router.get(
    "/v1/governance/bind-receipts/export",
    response_model=GovernanceBindReceiptExportResponse,
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def governance_bind_receipts_export(
    decision_id: str | None = Query(default=None),
    execution_intent_id: str | None = Query(default=None),
    target_path: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    lineage_query: str | None = Query(default=None),
    failed_only: str | None = Query(default=None),
    recent_only: str | None = Query(default=None),
    sort: str | None = Query(default=None),
):
    """Export bind receipts with list-equivalent filter and sort semantics."""
    try:
        parsed_outcome = _parse_bind_receipt_outcome(outcome)
        parsed_sort = _parse_bind_receipt_sort(sort)
        parsed_failed_only = _parse_bool_query(failed_only, field_name="failed_only")
        parsed_recent_only = _parse_bool_query(recent_only, field_name="recent_only")
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "invalid_bind_receipt_query",
                "detail": "invalid_query_parameter",
            },
        )

    try:
        receipts = find_bind_receipts(
            decision_id=decision_id,
            execution_intent_id=execution_intent_id,
        )
        filtered_items = _apply_bind_receipt_filters(
            receipts,
            target_path=target_path,
            target_type=target_type,
            outcome=parsed_outcome,
            reason_code=reason_code,
            lineage_query=lineage_query,
            failed_only=parsed_failed_only,
            recent_only=parsed_recent_only,
            sort=parsed_sort,
        )
        enriched_items = [enrich_bind_receipt_payload(item) for item in filtered_items]
        applied_filters = _bind_receipt_applied_filters(
            decision_id=decision_id,
            execution_intent_id=execution_intent_id,
            target_path=target_path,
            target_type=target_type,
            outcome=parsed_outcome,
            reason_code=reason_code,
            lineage_query=lineage_query,
            failed_only=parsed_failed_only,
            recent_only=parsed_recent_only,
        )
        return {
            "ok": True,
            "count": len(enriched_items),
            "items": enriched_items,
            "sort": parsed_sort,
            "applied_filters": applied_filters,
            "total_count": len(enriched_items),
            "target_catalog": get_target_catalog_payload(),
        }
    except Exception as exc:
        logger.error("governance_bind_receipts_export failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"ok": False, "error": "Failed to export bind receipts"})


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
        enriched_receipt = enrich_bind_receipt_payload(receipts[-1].to_dict())
        return {
            "ok": True,
            **build_bind_response_payload(enriched_receipt),
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
@requires_bind_boundary(
    target_path="/v1/governance/policy-bundles/promote",
    target_type="policy_bundle",
    target_path_type="policy_bundle_promotion",
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
        return {"ok": True, **build_bind_response_payload(receipt.to_dict())}
    except (ValueError, TypeError) as exc:
        logger.warning("governance_promote_policy_bundle validation error: %s", exc)
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_promotion_request"})
    except Exception as exc:
        logger.error("governance_promote_policy_bundle failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to promote policy bundle"},
        )


@router.get("/v1/governance/live-snapshot", dependencies=[Depends(require_permission(Permission.governance_read))])
def governance_live_snapshot() -> dict[str, Any]:
    """Return Mission Control governance live snapshot from backend artifacts."""
    return build_governance_live_snapshot()
