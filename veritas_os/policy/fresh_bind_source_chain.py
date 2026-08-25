"""Build a fresh, non-effecting prerequisite chain for Real Bind issuance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.live_adapter_dry_run_authority_evidence_linkage import (
    build_live_adapter_dry_run_authority_evidence_linkage_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    build_live_adapter_dry_run_bind_authorization_gate_review_packet,
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_bind_pre_dispatch_review import (
    build_live_adapter_dry_run_bind_pre_dispatch_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_credential_authorization import (
    build_live_adapter_dry_run_credential_authorization_evaluation_packet,
)
from veritas_os.policy.live_adapter_dry_run_dispatch_readiness import (
    build_live_adapter_dry_run_dispatch_readiness_packet,
)
from veritas_os.policy.live_adapter_dry_run_endpoint_allowlist import (
    build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
)
from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    build_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_linkage import (
    build_live_adapter_dry_run_human_approval_linkage_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_operator_dispatch_review import (
    build_live_adapter_dry_run_operator_dispatch_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_readiness import (
    build_live_adapter_dry_run_request_readiness_packet,
)
from veritas_os.policy.live_adapter_dry_run_request import (
    build_live_adapter_dry_run_request_packet,
)
from veritas_os.policy.reference_adapter_rehearsal import (
    verify_reference_adapter_in_memory_rehearsal_packet,
)


class FreshBindSourceChainError(ValueError):
    """Raised when the fresh source chain cannot preserve trusted identity."""


@dataclass(frozen=True)
class FreshBindSourceChainInputs:
    """Untrusted declarations consumed by existing production builders."""

    reference_rehearsal_packet: Any
    endpoint_candidate: Any
    endpoint_allowlist_snapshot: Any
    credential_reference: Any
    credential_policy_snapshot: Any
    operator_review_decision: Any
    bind_pre_dispatch_review_decision: Any
    authority_evidence_reference_bundle: Any
    human_approval_reference_bundle: Any
    final_readiness_review_decision: Any
    gate_review_decision: Any


def build_fresh_bind_source_chain(
    execution_intent: ExecutionIntent,
    inputs: FreshBindSourceChainInputs,
    *,
    built_at: datetime,
) -> Any:
    """Build and independently verify every non-effecting source-chain packet.

    IDs, hashes, lineage, and per-stage timestamps are derived by the existing
    builders. ``built_at`` is the sole clock input and is never copied from a
    caller declaration into trusted identity.
    """
    rehearsal = verify_reference_adapter_in_memory_rehearsal_packet(
        inputs.reference_rehearsal_packet
    )
    expected = execution_intent.to_dict()
    if (
        rehearsal.execution_intent != expected
        or rehearsal.execution_intent_id != execution_intent.execution_intent_id
        or rehearsal.execution_intent_hash != hash_execution_intent(execution_intent)
    ):
        raise FreshBindSourceChainError("FBS_EXECUTION_INTENT_MISMATCH")

    at = built_at
    readiness = build_live_adapter_dry_run_request_readiness_packet(rehearsal, at)
    request = build_live_adapter_dry_run_request_packet(readiness, at)
    dispatch = build_live_adapter_dry_run_dispatch_readiness_packet(request, at)
    endpoint = build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        dispatch, inputs.endpoint_candidate, inputs.endpoint_allowlist_snapshot, at
    )
    credential = build_live_adapter_dry_run_credential_authorization_evaluation_packet(
        endpoint, inputs.credential_reference, inputs.credential_policy_snapshot, at
    )
    operator = build_live_adapter_dry_run_operator_dispatch_review_packet(
        credential, inputs.operator_review_decision, at
    )
    pre_dispatch = build_live_adapter_dry_run_bind_pre_dispatch_review_packet(
        operator, inputs.bind_pre_dispatch_review_decision, at
    )
    authority = build_live_adapter_dry_run_authority_evidence_linkage_review_packet(
        pre_dispatch, inputs.authority_evidence_reference_bundle, at
    )
    human = build_live_adapter_dry_run_human_approval_linkage_review_packet(
        authority, inputs.human_approval_reference_bundle, at
    )
    final = build_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        human, inputs.final_readiness_review_decision, at
    )
    packet = build_live_adapter_dry_run_bind_authorization_gate_review_packet(
        final, inputs.gate_review_decision, at
    )
    verified = verify_live_adapter_dry_run_bind_authorization_gate_review_packet(packet)
    if (
        verified.execution_intent != expected
        or verified.execution_intent_id != execution_intent.execution_intent_id
        or verified.execution_intent_hash != hash_execution_intent(execution_intent)
    ):
        raise FreshBindSourceChainError("FBS_VERIFIED_INTENT_MISMATCH")
    return verified


def fresh_bind_proof_report(*, authorization_issued: bool) -> dict[str, bool]:
    """Return machine-readable claims without claiming an external effect."""
    return {
        "decision_lineage_proven": authorization_issued,
        "execution_intent_lineage_proven": authorization_issued,
        "authority_evidence_proven": authorization_issued,
        "revocation_checked": authorization_issued,
        "human_approval_proven": authorization_issued,
        "endpoint_binding_proven": authorization_issued,
        "adapter_contract_binding_proven": authorization_issued,
        "credential_reference_binding_proven": authorization_issued,
        "credential_scope_binding_proven": authorization_issued,
        "authorization_source_chain_proven": authorization_issued,
        "real_bind_authorization_issued": authorization_issued,
        "external_effect_performed": False,
        "real_decision_to_effect_e2e": False,
    }
