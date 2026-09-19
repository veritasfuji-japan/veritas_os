"""Run the bounded VERITAS / CAGE Phase 5D ESCALATE / Human Review proof.

This proof exercises the current source-pinned CAGE Provider03 adapter and
CAGE's real Redis-backed DeferQueue against the loopback VERITAS Phase 5A
runtime surface.

The proof deliberately demonstrates a non-amplification property:
CAGE human-review quorum can resolve the CAGE queue state, but it does not
create VERITAS AuthorityEvidence, HumanApprovalReceipt, BindAuthorization, or
execution permission. The stale VERITAS scenario is therefore re-evaluated
after CAGE quorum and must remain ESCALATE until the underlying stale evidence
is independently refreshed through a VERITAS-governed path.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Final

PHASE5D_PROOF_ID: Final[str] = "veritas-cage-provider03-phase5d-human-review-v1"
ESCALATE_SCENARIO: Final[str] = "scenario_d_stale_sanctions_screening"
MISSING_AUTHORITY_SCENARIO: Final[str] = "scenario_e_missing_authority"
MISSING_APPROVAL_SCENARIO: Final[str] = (
    "scenario_f_high_irreversibility_without_human_approval"
)
FIELD_MAP: Final[dict[str, str]] = {"amount": "magnitude", "symbol": "context"}
CONSENSUS_SCORE: Final[float] = 0.90


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return {str(key): _jsonable(item) for key, item in vars(value).items()}
    return value


def _load_cage(cage_repo: Path) -> dict[str, Any]:
    if not cage_repo.is_dir():
        raise RuntimeError(f"CAGE checkout not found: {cage_repo}")
    cage_path = str(cage_repo)
    if cage_path not in sys.path:
        sys.path.insert(0, cage_path)

    provider_module = importlib.import_module("src.integrations.provider_03.provider")
    normative_module = importlib.import_module("src.gateway.governance.normative_provider")
    defer_module = importlib.import_module("src.gateway.governance.defer_queue")
    return {
        "provider_module": provider_module,
        "provider_cls": getattr(provider_module, "Provider03NormativeProvider"),
        "enforce_fria_boundary": getattr(normative_module, "enforce_fria_boundary"),
        "defer_queue_cls": getattr(defer_module, "DeferQueue"),
        "approval_record_cls": getattr(defer_module, "ApprovalRecord"),
        "approval_status": getattr(defer_module, "ApprovalStatus"),
        "defer_reason": getattr(defer_module, "DeferReason"),
    }


def _payload(scenario_name: str) -> dict[str, Any]:
    return {
        "action": "aml_kyc_regulated_action",
        "veritas_scenario_name": scenario_name,
        "action_context": {"amount": 1000, "symbol": "acct"},
    }


def _needs_human_review(validation: Any) -> bool:
    findings = getattr(validation, "findings", None) or []
    return any(
        isinstance(finding, dict) and finding.get("needs_human_review") is True
        for finding in findings
    )


def _exposes_bind_receipt(validation: Any) -> bool:
    findings = getattr(validation, "findings", None) or []
    return any(
        isinstance(finding, dict) and isinstance(finding.get("bind_receipt"), dict)
        for finding in findings
    )


def _principal_hash(urn: str) -> str:
    return hashlib.sha256(urn.encode("utf-8")).hexdigest()


async def _run(
    *,
    cage: dict[str, Any],
    endpoint: str,
    token: str,
    redis_url: str,
) -> dict[str, Any]:
    import redis.asyncio as aioredis

    provider = cage["provider_cls"](
        endpoint=endpoint,
        api_key=token,
        timeout=2.0,
        action_context_field_map=FIELD_MAP,
    )
    redis_client = aioredis.from_url(redis_url, db=1, decode_responses=True)
    queue = cage["defer_queue_cls"](redis_client)

    try:
        await redis_client.flushdb()

        # Real CAGE adaptive boundary:
        # Provider03 ESCALATE -> admitted=False + needs_human_review ->
        # EXTERNAL_HOLD parked in the real Redis-backed DeferQueue.
        boundary = await cage["enforce_fria_boundary"](
            provider=provider,
            action_context=_payload(ESCALATE_SCENARIO),
            consensus_score=CONSENSUS_SCORE,
            defer_queue=queue,
            thread_id="phase5d::stale-sanctions",
        )
        boundary_status = str(getattr(boundary.status, "value", boundary.status))
        hold_id = str(boundary.defer_id or "")
        if boundary_status != "DEFER" or boundary.path != "SYNC_GATE_REVIEW" or not hold_id:
            raise RuntimeError(
                "CAGE did not route VERITAS ESCALATE into the expected DEFER review path"
            )

        validation = boundary.validation
        if validation is None:
            raise RuntimeError("Phase 5D boundary returned no Provider03 validation")
        if getattr(validation, "admitted", True) is not False:
            raise RuntimeError("ESCALATE validation was unexpectedly admitted")
        if not _needs_human_review(validation):
            raise RuntimeError("ESCALATE validation lost needs_human_review marker")
        if _exposes_bind_receipt(validation):
            raise RuntimeError("ESCALATE validation exposed a BindReceipt")

        hold_token = await queue.get_token(hold_id)
        if hold_token is None:
            raise RuntimeError("CAGE EXTERNAL_HOLD token was not persisted")
        hold_status = await redis_client.hget(f"DEFER:{hold_id}", "status")
        if hold_status != "PARKED":
            raise RuntimeError(f"expected PARKED hold token, got {hold_status!r}")
        if str(getattr(hold_token.defer_reason, "value", hold_token.defer_reason)) != "EXTERNAL_HOLD":
            raise RuntimeError("CAGE review token is not EXTERNAL_HOLD")
        if int(hold_token.required_quorum) != 3:
            raise RuntimeError("CAGE EXTERNAL_HOLD quorum is not 3")

        approval_record_cls = cage["approval_record_cls"]
        approval_status = cage["approval_status"]
        approvers = [
            "urn:veritas:phase5d:reviewer:one",
            "urn:veritas:phase5d:reviewer:two",
            "urn:veritas:phase5d:reviewer:three",
        ]
        approval_results: list[dict[str, Any]] = []

        first_record = approval_record_cls(
            approver_urn=approvers[0],
            approved_at_utc="2026-09-19T00:00:01+00:00",
            auth_method="OIDC",
            auth_principal_hash=_principal_hash(approvers[0]),
        )
        first_status, first_token = await queue.approve(hold_id, first_record)
        approval_results.append(
            {
                "approver_urn": approvers[0],
                "status": str(getattr(first_status, "value", first_status)),
                "approval_count": len(first_token.approvals) if first_token else 0,
            }
        )
        if first_status != approval_status.PARTIAL_QUORUM:
            raise RuntimeError("first CAGE approval did not remain partial")

        duplicate_status, duplicate_token = await queue.approve(hold_id, first_record)
        if duplicate_status != approval_status.ALREADY_APPROVED:
            raise RuntimeError("duplicate CAGE approver was not rejected")
        if duplicate_token is None or len(duplicate_token.approvals) != 1:
            raise RuntimeError("duplicate CAGE approval changed approval count")

        for index, approver in enumerate(approvers[1:], start=2):
            record = approval_record_cls(
                approver_urn=approver,
                approved_at_utc=f"2026-09-19T00:00:0{index}+00:00",
                auth_method="OIDC",
                auth_principal_hash=_principal_hash(approver),
            )
            status, updated = await queue.approve(hold_id, record)
            approval_results.append(
                {
                    "approver_urn": approver,
                    "status": str(getattr(status, "value", status)),
                    "approval_count": len(updated.approvals) if updated else 0,
                }
            )
            expected = (
                approval_status.QUORUM_REACHED
                if index == 3
                else approval_status.PARTIAL_QUORUM
            )
            if status != expected:
                raise RuntimeError(
                    f"CAGE approval {index} returned {status!r}, expected {expected!r}"
                )

        resolved_status = await redis_client.hget(f"DEFER:{hold_id}", "status")
        resolved_token = await queue.get_token(hold_id)
        if resolved_status != "RESOLVED" or resolved_token is None:
            raise RuntimeError("CAGE review quorum did not resolve the hold token")
        if len(resolved_token.approvals) != 3:
            raise RuntimeError("resolved CAGE token does not contain three approvals")

        # Critical non-amplification proof:
        # CAGE quorum is NOT fed into VERITAS as authority/approval. Re-evaluate
        # the unchanged stale scenario through the real Provider03 HTTP path.
        stale_recheck = await provider.validate_fria(_payload(ESCALATE_SCENARIO))
        if getattr(stale_recheck, "admitted", True) is not False:
            raise RuntimeError("CAGE human-review quorum improperly amplified to VERITAS admission")
        if not _needs_human_review(stale_recheck):
            raise RuntimeError("stale VERITAS evidence no longer requires review after CAGE quorum")
        if _exposes_bind_receipt(stale_recheck):
            raise RuntimeError("post-quorum stale recheck exposed a BindReceipt")

        missing_authority = await provider.validate_fria(_payload(MISSING_AUTHORITY_SCENARIO))
        if getattr(missing_authority, "admitted", True) is not False:
            raise RuntimeError("missing authority was admitted after CAGE review")
        if _exposes_bind_receipt(missing_authority):
            raise RuntimeError("missing-authority result exposed a BindReceipt")

        missing_approval = await provider.validate_fria(_payload(MISSING_APPROVAL_SCENARIO))
        if getattr(missing_approval, "admitted", True) is not False:
            raise RuntimeError("missing VERITAS human approval was admitted")
        if _exposes_bind_receipt(missing_approval):
            raise RuntimeError("missing-approval result exposed a BindReceipt")

        checks = {
            "provider03_escalate_non_admitted": getattr(validation, "admitted", True) is False,
            "provider03_escalate_marks_human_review": _needs_human_review(validation),
            "cage_boundary_routes_to_defer": boundary_status == "DEFER",
            "cage_boundary_path_is_sync_gate_review": boundary.path == "SYNC_GATE_REVIEW",
            "cage_external_hold_persisted": hold_token is not None and hold_status == "PARKED",
            "cage_external_hold_requires_three_approvers": int(hold_token.required_quorum) == 3,
            "duplicate_approver_rejected": duplicate_status == approval_status.ALREADY_APPROVED,
            "cage_quorum_resolves_queue_state": resolved_status == "RESOLVED",
            "cage_quorum_does_not_create_veritas_admission": (
                getattr(stale_recheck, "admitted", True) is False
            ),
            "stale_evidence_still_escalates_after_cage_quorum": _needs_human_review(stale_recheck),
            "escalate_path_exposes_no_bind_receipt": not _exposes_bind_receipt(validation),
            "post_quorum_stale_recheck_exposes_no_bind_receipt": (
                not _exposes_bind_receipt(stale_recheck)
            ),
            "missing_authority_remains_denied": getattr(missing_authority, "admitted", True) is False,
            "missing_veritas_approval_remains_denied": getattr(missing_approval, "admitted", True) is False,
        }
        blockers = sorted(key for key, passed in checks.items() if passed is not True)

        return {
            "phase5d_status": "READY_FOR_PHASE5E" if not blockers else "BLOCKED_PHASE5D",
            "phase5d_blockers": blockers,
            "checks": checks,
            "initial_boundary": {
                "status": boundary_status,
                "path": boundary.path,
                "defer_id": hold_id,
                "validation": _jsonable(validation),
            },
            "cage_human_review": {
                "defer_reason": str(
                    getattr(hold_token.defer_reason, "value", hold_token.defer_reason)
                ),
                "required_quorum": int(hold_token.required_quorum),
                "approval_results": approval_results,
                "duplicate_approval_status": str(
                    getattr(duplicate_status, "value", duplicate_status)
                ),
                "final_queue_status": resolved_status,
                "resolution": resolved_token.resolution,
                "synthetic_operator_records": True,
                "live_human_identity_claim": False,
            },
            "veritas_post_quorum_recheck": _jsonable(stale_recheck),
            "negative_rechecks": {
                "missing_authority": _jsonable(missing_authority),
                "missing_veritas_human_approval": _jsonable(missing_approval),
            },
        }
    finally:
        await redis_client.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cage-repo", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--veritas-source-sha", required=True)
    parser.add_argument("--cage-source-sha", required=True)
    parser.add_argument("--phase5c-veritas-baseline", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cage = _load_cage(args.cage_repo.resolve())
    report_body = asyncio.run(
        _run(
            cage=cage,
            endpoint=args.endpoint.rstrip("/"),
            token=args.token,
            redis_url=args.redis_url,
        )
    )

    report = {
        "format_version": "veritas-cage-phase5d-runtime/v1",
        "proof_id": PHASE5D_PROOF_ID,
        "veritas_source_sha": args.veritas_source_sha,
        "cage_source_sha": args.cage_source_sha,
        "phase5c_veritas_baseline": args.phase5c_veritas_baseline,
        "cage_provider03_module": str(Path(cage["provider_module"].__file__).resolve()),
        "runtime_topology": (
            "real CAGE enforce_fria_boundary -> real CAGE Provider03 -> loopback VERITAS "
            "-> real Redis-backed CAGE DeferQueue -> synthetic distinct operator quorum "
            "-> fresh Provider03 re-evaluation of unchanged VERITAS evidence"
        ),
        "real_cage_provider03_client": True,
        "real_cage_defer_queue": True,
        "real_redis_queue": True,
        "real_cage_fria_boundary": True,
        "loopback_http": True,
        "mocked_cage_http_client": False,
        "external_effects_executed": False,
        "bind_receipt_created_on_escalate": False,
        "evidence_submitted_on_escalate": False,
        "cage_human_review_is_veritas_authority": False,
        "cage_human_review_is_veritas_human_approval": False,
        "production_claim": False,
        "google_endorsement_claim": False,
        "commercial_integration_claim": False,
        **report_body,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "phase5d-runtime-report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
