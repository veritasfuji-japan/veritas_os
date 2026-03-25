# veritas_os/api/routes_governance.py
"""Governance policy API endpoints with RBAC/ABAC support."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

# Governance functions accessed via _get_server() for test monkeypatching compat

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


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


def require_governance_access(
    x_role: Optional[str] = Header(default=None, alias="X-Role"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> bool:
    """Enforce governance RBAC/ABAC constraints for admin endpoints."""
    if not _governance_rbac_enabled():
        logger.warning(
            "SECURITY WARNING: governance RBAC/ABAC is disabled by "
            "VERITAS_GOVERNANCE_ENFORCE_RBAC=0"
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

@router.get("/v1/governance/value-drift")
def governance_value_drift(telos_baseline: float = Query(default=0.5, ge=0.0, le=1.0)):
    """Return ValueCore drift metrics against a Telos baseline."""
    srv = _get_server()
    try:
        result = srv.get_value_drift(telos_baseline=telos_baseline)
        return {"ok": True, "value_drift": result}
    except Exception as e:
        logger.error("governance_value_drift failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load value drift metrics"},
        )


@router.get("/v1/governance/policy")
def governance_get():
    """Return the current governance policy."""
    srv = _get_server()
    try:
        policy = srv.get_policy()
        return {"ok": True, "policy": policy}
    except Exception as e:
        logger.error("governance_get failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load governance policy"},
        )


@router.put("/v1/governance/policy")
def governance_put(body: dict):
    """Update the governance policy (partial merge)."""
    srv = _get_server()
    try:
        srv.enforce_four_eyes_approval(body)
        previous = srv.get_policy()
        updated = srv.update_policy(body)
        srv._publish_event(
            "governance.updated",
            {"updated_by": updated.get("updated_by", "api")},
        )
        _emit_governance_change_alert(previous=previous, updated=updated)
        return {"ok": True, "policy": updated}
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
            content={"ok": False, "error": "governance policy validation failed"},
        )
    except Exception as e:
        logger.error("governance_put failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to update governance policy"},
        )


@router.get("/v1/governance/policy/history")
def governance_policy_history(limit: int = Query(default=50, ge=1, le=500)):
    """Return recent governance policy change history (newest first)."""
    srv = _get_server()
    try:
        records = srv.get_policy_history(limit=limit)
        return {"ok": True, "count": len(records), "history": records}
    except Exception as e:
        logger.error("governance_policy_history failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Failed to load governance policy history"},
        )
