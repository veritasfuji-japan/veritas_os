"""Deterministic AML/KYC regulated action path fixture orchestration.

This module provides a fully synthetic, side-effect-free end-to-end fixture that
walks the regulated action path from AI-assisted risk detection through commit
boundary evaluation and bind-receipt enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from veritas_os.governance.action_contracts import ActionClassContract, load_action_class_contract
from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult
from veritas_os.governance.commit_boundary import CommitBoundaryResult, evaluate_commit_boundary
from veritas_os.security.hash import sha256_of_canonical_json

DEFAULT_CONTRACT_PATH = Path("policies/action_contracts/aml_kyc_customer_risk_escalation.v1.yaml")
DEFAULT_FIXTURE_PATH = Path(
    "veritas_os/sample_data/governance/aml_kyc_regulated_action_path/scenarios.json"
)
FIXTURE_NOW = datetime.fromisoformat("2026-04-26T00:00:00")


@dataclass(frozen=True)
class RegulatedActionPathResult:
    """Inspectable deterministic result of one regulated action scenario."""

    scenario_name: str
    expected_outcome: str
    actual_outcome: str
    action_contract_id: str
    authority_evidence_id: str
    bind_receipt_id: str
    commit_boundary_result: str
    failed_predicate_count: int
    stale_predicate_count: int
    missing_predicate_count: int
    refusal_basis: list[str]
    escalation_basis: list[str]
    trustlog_lineage_ref: str
    decision_artifact_id: str
    risk_detection_summary: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize result as JSON-ready mapping."""
        return {
            "scenario_name": self.scenario_name,
            "expected_outcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome,
            "action_contract_id": self.action_contract_id,
            "authority_evidence_id": self.authority_evidence_id,
            "bind_receipt_id": self.bind_receipt_id,
            "commit_boundary_result": self.commit_boundary_result,
            "failed_predicate_count": self.failed_predicate_count,
            "stale_predicate_count": self.stale_predicate_count,
            "missing_predicate_count": self.missing_predicate_count,
            "refusal_basis": self.refusal_basis,
            "escalation_basis": self.escalation_basis,
            "trustlog_lineage_ref": self.trustlog_lineage_ref,
            "decision_artifact_id": self.decision_artifact_id,
            "risk_detection_summary": self.risk_detection_summary,
            "metadata": self.metadata,
        }


def load_regulated_action_scenarios(path: Path = DEFAULT_FIXTURE_PATH) -> list[dict[str, Any]]:
    """Load deterministic AML/KYC regulated action scenarios."""
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("regulated action fixture must include non-empty 'scenarios'")
    return scenarios


def run_regulated_action_scenario(
    scenario: dict[str, Any],
    *,
    action_contract: ActionClassContract,
) -> RegulatedActionPathResult:
    """Run one deterministic regulated-action scenario end to end."""
    scenario_name = str(scenario["scenario_name"])
    expected_outcome = str(scenario["expected_outcome"])
    requested_scope = [str(item) for item in scenario.get("requested_scope", [])]
    scenario_contract = _merge_contract_overrides(action_contract, scenario)

    risk_detection_summary = _build_risk_detection_summary(scenario)
    decision_artifact = _build_decision_artifact(scenario, risk_detection_summary)
    execution_intent = {
        "execution_intent_id": f"ei::{scenario_name}",
        "action_class": action_contract.action_class,
        "requested_scope": requested_scope,
        "admissible": True,
        "decision_artifact_id": decision_artifact["decision_artifact_id"],
    }

    authority_evidence = _build_authority_evidence(scenario, action_contract)
    evaluation = evaluate_commit_boundary(
        execution_intent=execution_intent,
        action_contract=scenario_contract,
        authority_evidence=authority_evidence,
        requested_scope=requested_scope,
        required_evidence_metadata=dict(scenario.get("required_evidence_metadata", {})),
        evidence_freshness_metadata=dict(scenario.get("evidence_freshness_metadata", {})),
        policy_snapshot_id=scenario.get("policy_snapshot_id"),
        actor_identity=scenario.get("actor_identity"),
        human_approval_state=dict(scenario.get("human_approval_state", {})),
        bind_context_metadata=dict(scenario.get("bind_context_metadata", {})),
        now=FIXTURE_NOW,
    )

    bind_receipt = _build_bind_receipt(scenario_name, evaluation)
    trustlog_lineage_ref = f"trustlog://bind/{bind_receipt['bind_receipt_id']}"

    return RegulatedActionPathResult(
        scenario_name=scenario_name,
        expected_outcome=expected_outcome,
        actual_outcome=evaluation.commit_boundary_result,
        action_contract_id=evaluation.action_contract_id,
        authority_evidence_id=evaluation.authority_evidence_id,
        bind_receipt_id=bind_receipt["bind_receipt_id"],
        commit_boundary_result=evaluation.commit_boundary_result,
        failed_predicate_count=len(evaluation.failed_predicates),
        stale_predicate_count=len(evaluation.stale_predicates),
        missing_predicate_count=len(evaluation.missing_predicates),
        refusal_basis=evaluation.refusal_basis,
        escalation_basis=evaluation.escalation_basis,
        trustlog_lineage_ref=trustlog_lineage_ref,
        decision_artifact_id=decision_artifact["decision_artifact_id"],
        risk_detection_summary=risk_detection_summary,
        metadata={
            "authority_evidence_hash": bind_receipt["authority_evidence_hash"],
            "refusal_or_escalation_basis": (
                evaluation.refusal_basis or evaluation.escalation_basis
            ),
        },
    )


def run_all_regulated_action_scenarios(
    *,
    scenarios: list[dict[str, Any]] | None = None,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> list[RegulatedActionPathResult]:
    """Run all deterministic fixture scenarios with one shared action contract."""
    contract = load_action_class_contract(contract_path)
    scenario_list = scenarios or load_regulated_action_scenarios(fixture_path)
    return [
        run_regulated_action_scenario(scenario, action_contract=contract)
        for scenario in scenario_list
    ]


def _build_risk_detection_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    risk_flags = dict(scenario.get("risk_flags", {}))
    risk_score = int(scenario.get("risk_score", 0))
    triggered_flags = sorted([key for key, enabled in risk_flags.items() if bool(enabled)])
    return {
        "risk_score": risk_score,
        "risk_band": "high" if risk_score >= 80 else "medium" if risk_score >= 40 else "low",
        "triggered_flags": triggered_flags,
    }


def _build_decision_artifact(
    scenario: dict[str, Any],
    risk_detection_summary: dict[str, Any],
) -> dict[str, Any]:
    scenario_name = str(scenario["scenario_name"])
    artifact_id = f"decision::{scenario_name}"
    return {
        "decision_artifact_id": artifact_id,
        "risk_detection_summary": risk_detection_summary,
        "policy_snapshot_id": scenario.get("policy_snapshot_id", ""),
    }


def _build_authority_evidence(
    scenario: dict[str, Any],
    action_contract: ActionClassContract,
) -> AuthorityEvidence | None:
    authority_payload = scenario.get("authority_evidence")
    if not isinstance(authority_payload, dict):
        return None

    verification = VerificationResult(str(authority_payload.get("verification_result", "valid")))
    evidence = AuthorityEvidence(
        authority_evidence_id=str(authority_payload["authority_evidence_id"]),
        action_contract_id=action_contract.id,
        action_contract_version=action_contract.version,
        actor_identity=str(scenario.get("actor_identity", "")),
        actor_role=str(authority_payload.get("actor_role", "aml_reviewer")),
        authority_source_refs=list(authority_payload.get("authority_source_refs", [])),
        role_or_policy_basis=list(authority_payload.get("role_or_policy_basis", [])),
        scope_grants=list(authority_payload.get("scope_grants", [])),
        scope_limitations=list(authority_payload.get("scope_limitations", [])),
        validity_window=dict(authority_payload.get("validity_window", {})),
        issued_at=str(authority_payload.get("issued_at", "")),
        valid_from=str(authority_payload.get("valid_from", "")),
        valid_until=str(authority_payload.get("valid_until", "")),
        revalidated_at=authority_payload.get("revalidated_at"),
        policy_snapshot_id=scenario.get("policy_snapshot_id"),
        evidence_hash=str(authority_payload.get("evidence_hash", "")),
        verification_result=verification,
        failure_reasons=list(authority_payload.get("failure_reasons", [])),
        metadata=dict(authority_payload.get("metadata", {})),
    )
    if not evidence.evidence_hash:
        digest = evidence.deterministic_digest()
        payload = evidence.to_dict()
        payload["verification_result"] = verification
        payload["evidence_hash"] = digest
        return AuthorityEvidence(**payload)
    return evidence


def _build_bind_receipt(scenario_name: str, result: CommitBoundaryResult) -> dict[str, str]:
    payload = {
        "bind_receipt_id": f"bind::{scenario_name}",
        "action_contract_id": result.action_contract_id,
        "authority_evidence_id": result.authority_evidence_id,
        "authority_evidence_hash": result.authority_evidence_hash,
        "commit_boundary_result": result.commit_boundary_result,
    }
    payload["bind_receipt_hash"] = sha256_of_canonical_json(payload)
    return payload


def _merge_contract_overrides(
    base: ActionClassContract,
    scenario: dict[str, Any],
) -> ActionClassContract:
    overrides = scenario.get("contract_overrides")
    payload = base.to_dict()
    irreversibility = dict(payload.get("irreversibility", {}))
    if not str(irreversibility.get("boundary", "")).strip():
        irreversibility["boundary"] = "internal_escalation_dispatch"
    if not str(irreversibility.get("level", "")).strip():
        irreversibility["level"] = "medium"
    payload["irreversibility"] = irreversibility
    if not isinstance(overrides, dict) or not overrides:
        return ActionClassContract(**payload)
    payload.update(overrides)
    return ActionClassContract(**payload)
