"""VERITAS / CAGE Phase 5A Provider03-compatible runtime surface.

This module provides the first source-pinned HTTP boundary used by the Phase 5
runtime prototype.  It intentionally stays local/sandbox-only and reuses the
existing deterministic VERITAS regulated-action governance path.

It does NOT create execution authority, perform an external business effect,
claim production readiness, or create a TrustLog witness.  The endpoints mirror
the CAGE Provider03 HTTP contract so the real CAGE Provider03 client can talk to
a VERITAS runtime process over loopback HTTP.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any, Final

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from veritas_os.governance.regulated_action_path import (
    DEFAULT_CONTRACT_PATH,
    DEFAULT_FIXTURE_PATH,
    RegulatedActionPathResult,
    run_all_regulated_action_scenarios,
)
from veritas_os.security.hash import sha256_of_canonical_json

PHASE5A_PROOF_ID: Final[str] = "veritas-cage-provider03-phase5a-runtime-v1"
VERITAS_SOURCE_BASELINE: Final[str] = "26837ad8fbb462d4163116e41b6fdfc9dcaa9431"
CAGE_PHASE4_APPROVED_BASELINE: Final[str] = (
    "5f54d5e3403d67101e028ed14fa8dade853fb221"
)
CAGE_PROVIDER03_PATH: Final[str] = "src/integrations/provider_03/provider.py"
TOKEN_ENV: Final[str] = "VERITAS_CAGE_PHASE5_BEARER_TOKEN"

_OUTCOME_TO_VERDICT: Final[dict[str, str]] = {
    "commit": "APPROVED",
    "escalate": "ESCALATE",
    "block": "REJECTED",
    "refuse": "REJECTED",
}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = _REPO_ROOT / DEFAULT_FIXTURE_PATH
_CONTRACT_PATH = _REPO_ROOT / DEFAULT_CONTRACT_PATH


class Phase5AEvidenceRequest(BaseModel):
    """Provider03 evidence submission body used by the local prototype."""

    evidence_hash: str = Field(min_length=1, max_length=256)


def _require_configured_token(explicit_token: str | None) -> str:
    token = (explicit_token if explicit_token is not None else os.environ.get(TOKEN_ENV, "")).strip()
    if not token:
        raise RuntimeError(
            f"{TOKEN_ENV} must be configured for the Phase 5A runtime prototype"
        )
    return token


def _scenario_name_from_payload(payload: dict[str, Any]) -> str:
    direct = payload.get("veritas_scenario_name") or payload.get("scenario_name")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    action_context = payload.get("action_context")
    if isinstance(action_context, dict):
        nested = action_context.get("veritas_scenario_name") or action_context.get(
            "scenario_name"
        )
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _run_scenario(scenario_name: str) -> RegulatedActionPathResult | None:
    """Execute the existing deterministic VERITAS governance path for one fixture."""

    results = run_all_regulated_action_scenarios(
        fixture_path=_FIXTURE_PATH,
        contract_path=_CONTRACT_PATH,
    )
    for result in results:
        if result.scenario_name == scenario_name:
            return result
    return None

def _bind_receipt_for_result(result: RegulatedActionPathResult) -> dict[str, str]:
    """Reconstruct the deterministic VERITAS bind receipt for runtime handoff.

    The VERITAS receipt hash covers the receipt body before the
    ``bind_receipt_hash`` field itself is inserted. CAGE later computes a
    separate JCS/SHA-256 digest over the complete receipt.
    """

    body = {
        "bind_receipt_id": result.bind_receipt_id,
        "action_contract_id": result.action_contract_id,
        "authority_evidence_id": result.authority_evidence_id,
        "authority_evidence_hash": str(result.metadata.get("authority_evidence_hash", "")),
        "commit_boundary_result": result.commit_boundary_result,
    }
    receipt = dict(body)
    receipt["bind_receipt_hash"] = sha256_of_canonical_json(body)
    return receipt


def _finding_for_result(result: RegulatedActionPathResult) -> dict[str, Any]:
    if result.actual_outcome == "commit":
        code = "veritas.commit_boundary"
        severity = "info"
    elif result.actual_outcome == "escalate":
        code = "veritas.escalation_required"
        severity = "review"
    else:
        code = "veritas.bind_blocked"
        severity = "blocked"

    finding = {
        "code": code,
        "severity": severity,
        "scenario_name": result.scenario_name,
        "commit_boundary_result": result.commit_boundary_result,
        "bind_receipt_id": result.bind_receipt_id,
        "authority_evidence_id": result.authority_evidence_id,
        "failed_predicate_count": result.failed_predicate_count,
        "stale_predicate_count": result.stale_predicate_count,
        "missing_predicate_count": result.missing_predicate_count,
        "refusal_basis": list(result.refusal_basis),
        "escalation_basis": list(result.escalation_basis),
        "phase5a_runtime_prototype": True,
        "external_effect_executed": False,
    }
    if result.actual_outcome == "commit":
        finding["bind_receipt"] = _bind_receipt_for_result(result)
        finding["bind_receipt_hash_semantics"] = (
            "VERITAS canonical body hash before bind_receipt_hash insertion"
        )
    return finding


def _runtime_manifest() -> dict[str, Any]:
    return {
        "proof_id": PHASE5A_PROOF_ID,
        "veritas_source_baseline": VERITAS_SOURCE_BASELINE,
        "cage_phase4_approved_baseline": CAGE_PHASE4_APPROVED_BASELINE,
        "cage_provider03_path": CAGE_PROVIDER03_PATH,
        "runtime_topology": "CAGE Provider03 -> loopback HTTP -> VERITAS Phase5A surface",
        "production_claim": False,
        "live_external_effects": False,
        "google_endorsement_claim": False,
        "trustlog_witness_claim": False,
    }


def create_phase5a_app(*, bearer_token: str | None = None) -> FastAPI:
    """Create the local Provider03-compatible Phase 5A FastAPI application.

    Authentication intentionally matches the current CAGE Provider03 adapter:
    ``Authorization: Bearer <token>``.  The token must be explicitly supplied
    or configured via :data:`TOKEN_ENV`; startup fails closed when absent.
    """

    expected_token = _require_configured_token(bearer_token)
    app = FastAPI(
        title="VERITAS / CAGE Phase 5A Runtime Prototype",
        version="0.1.0",
    )
    app.state.phase5a_runtime_manifest = _runtime_manifest()

    async def require_bearer(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> None:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="provider03_bearer_required")
        supplied = authorization[len("Bearer ") :]
        if not hmac.compare_digest(supplied, expected_token):
            raise HTTPException(status_code=401, detail="provider03_bearer_invalid")

    auth = [Depends(require_bearer)]

    @app.get("/baseline/{region}", dependencies=auth)
    async def fetch_baseline(region: str, response: Response) -> dict[str, Any]:
        profile = {
            "provider": "VERITAS_OS",
            "prototype_phase": "5A",
            "region": region,
            "decision_boundary": "regulated_action_governance",
            "execution_authority_created": False,
            "external_effects_enabled": False,
        }
        response.headers["ETag"] = hashlib.sha256(
            sha256_of_canonical_json(profile).encode("utf-8")
        ).hexdigest()
        return {"profile": profile}

    @app.post("/validate", dependencies=auth)
    async def validate(payload: dict[str, Any]) -> dict[str, Any]:
        scenario_name = _scenario_name_from_payload(payload)
        if not scenario_name:
            return {
                "verdict": "REJECTED",
                "findings": [
                    {
                        "code": "veritas.phase5a.scenario_missing",
                        "severity": "blocked",
                        "message": "veritas_scenario_name is required for the Phase 5A prototype",
                    }
                ],
            }

        result = _run_scenario(scenario_name)
        if result is None:
            return {
                "verdict": "REJECTED",
                "findings": [
                    {
                        "code": "veritas.phase5a.scenario_unknown",
                        "severity": "blocked",
                        "message": "unknown Phase 5A regulated-action scenario",
                        "scenario_name": scenario_name,
                    }
                ],
            }

        verdict = _OUTCOME_TO_VERDICT.get(result.actual_outcome, "REJECTED")
        finding = _finding_for_result(result)
        if result.actual_outcome not in _OUTCOME_TO_VERDICT:
            finding["code"] = "veritas.phase5a.unmapped_outcome"
            finding["severity"] = "blocked"
            finding["unmapped_outcome"] = result.actual_outcome
        return {"verdict": verdict, "findings": [finding]}

    @app.post("/evidence/{thread_id}", dependencies=auth)
    async def submit_evidence(
        thread_id: str,
        body: Phase5AEvidenceRequest,
    ) -> dict[str, str]:
        # This deterministic receipt proves only that the local prototype
        # accepted the evidence reference.  It is not a TrustLog witness,
        # signature, authority artifact, or production attestation.
        seal_hash = sha256_of_canonical_json(
            {
                "phase5a_proof_id": PHASE5A_PROOF_ID,
                "thread_id": thread_id,
                "evidence_hash": body.evidence_hash,
                "trustlog_proof_status": "lineage_only",
            }
        )
        return {"seal_hash": seal_hash}

    @app.get("/phase5a/manifest", dependencies=auth)
    async def runtime_manifest() -> dict[str, Any]:
        return dict(app.state.phase5a_runtime_manifest)

    return app
