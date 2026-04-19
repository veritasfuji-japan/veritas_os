"""WAT shadow issuance/validation/revocation API endpoints."""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from veritas_os.api.auth import require_permission
from veritas_os.api.rbac import Permission
from veritas_os.audit.wat_events import (
    SUPPORTED_WAT_EVENT_TYPES,
    get_wat_event,
    list_wat_events,
    persist_wat_issuance_event,
    persist_wat_replay_event,
    persist_wat_revocation_event,
    persist_wat_validation_event,
)

router = APIRouter()


class WatIssueShadowRequest(BaseModel):
    """Request body for shadow WAT issuance telemetry."""

    wat_id: Optional[str] = None
    psid: str = Field(min_length=1, max_length=500)
    observable_digest: Optional[str] = Field(default=None, max_length=500)
    ttl_seconds: int = Field(default=300, ge=1, le=86_400)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WatValidateShadowRequest(BaseModel):
    """Request body for shadow WAT validation telemetry."""

    wat_id: str = Field(min_length=1, max_length=500)
    outcome_event: str = Field(default="wat_validated")
    psid: Optional[str] = Field(default=None, max_length=500)
    observable_digest: Optional[str] = Field(default=None, max_length=500)
    details: Dict[str, Any] = Field(default_factory=dict)


class WatRevocationRequest(BaseModel):
    """Request body for WAT revocation transitions."""

    confirmed: bool = True
    reason: str = Field(default="", max_length=2000)
    details: Dict[str, Any] = Field(default_factory=dict)


def _actor_from_request(request: Request) -> str:
    """Derive stable actor label from request state set by RBAC dependency."""
    role = getattr(getattr(request, "state", None), "rbac_role", None)
    if isinstance(role, str) and role.strip():
        return f"api:{role.strip()}"
    return "api:unknown"


@router.post(
    "/v1/wat/issue-shadow",
    dependencies=[Depends(require_permission(Permission.decide))],
)
def issue_shadow_wat(body: WatIssueShadowRequest, request: Request) -> Dict[str, Any]:
    """Persist shadow-only WAT issuance telemetry."""
    wat_id = body.wat_id or f"wat_{uuid4().hex}"
    event = persist_wat_issuance_event(
        wat_id=wat_id,
        actor=_actor_from_request(request),
        details={
            "psid": body.psid,
            "observable_digest": body.observable_digest,
            "ttl_seconds": body.ttl_seconds,
            "metadata": body.metadata,
            "mode": "shadow",
        },
    )
    return {"ok": True, "wat_id": wat_id, "event": event}


@router.post(
    "/v1/wat/validate-shadow",
    dependencies=[Depends(require_permission(Permission.decide))],
)
def validate_shadow_wat(body: WatValidateShadowRequest, request: Request) -> Dict[str, Any]:
    """Persist shadow-only WAT validation telemetry."""
    if body.outcome_event == "wat_replay_suspected":
        event = persist_wat_replay_event(
            wat_id=body.wat_id,
            actor=_actor_from_request(request),
            details={
                "psid": body.psid,
                "observable_digest": body.observable_digest,
                "mode": "shadow",
                **body.details,
            },
        )
        return {"ok": True, "wat_id": body.wat_id, "event": event}

    if body.outcome_event not in SUPPORTED_WAT_EVENT_TYPES:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": "unsupported outcome_event"},
        )

    status = "ok" if body.outcome_event == "wat_validated" else "warning"
    event = persist_wat_validation_event(
        wat_id=body.wat_id,
        actor=_actor_from_request(request),
        event_type=body.outcome_event,
        status=status,
        details={
            "psid": body.psid,
            "observable_digest": body.observable_digest,
            "mode": "shadow",
            **body.details,
        },
    )
    return {"ok": True, "wat_id": body.wat_id, "event": event}


@router.get(
    "/v1/wat/events",
    dependencies=[Depends(require_permission(Permission.trust_log_read))],
)
def get_wat_events(
    wat_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    """List WAT event lane records."""
    events = list_wat_events(wat_id=wat_id, event_type=event_type, limit=limit)
    return {"ok": True, "items": events, "count": len(events)}


@router.get(
    "/v1/wat/{wat_id}",
    dependencies=[Depends(require_permission(Permission.trust_log_read))],
)
def get_wat_by_id(wat_id: str) -> Dict[str, Any]:
    """Return latest WAT event and recent timeline for a WAT id."""
    latest = get_wat_event(wat_id)
    if latest is None:
        return JSONResponse(status_code=404, content={"ok": False, "error": "wat_not_found"})

    timeline = list_wat_events(wat_id=wat_id, limit=50)
    return {
        "ok": True,
        "wat_id": wat_id,
        "latest": latest,
        "timeline": timeline,
    }


@router.post(
    "/v1/wat/revocation/{wat_id}",
    dependencies=[Depends(require_permission(Permission.decide))],
)
def revoke_wat(wat_id: str, body: WatRevocationRequest, request: Request) -> Dict[str, Any]:
    """Persist shadow revocation events (pending + optional confirmed)."""
    actor = _actor_from_request(request)
    pending = persist_wat_revocation_event(
        wat_id=wat_id,
        actor=actor,
        confirmed=False,
        details={"mode": "shadow", "reason": body.reason, **body.details},
    )

    confirmed_event: Optional[Dict[str, Any]] = None
    if body.confirmed:
        confirmed_event = persist_wat_revocation_event(
            wat_id=wat_id,
            actor=actor,
            confirmed=True,
            details={"mode": "shadow", "reason": body.reason, **body.details},
        )

    return {
        "ok": True,
        "wat_id": wat_id,
        "pending": pending,
        "confirmed": confirmed_event,
    }
