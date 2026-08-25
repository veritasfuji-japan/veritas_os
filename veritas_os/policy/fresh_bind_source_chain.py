"""Build a fresh, non-effecting prerequisite chain for Real Bind issuance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from veritas_os.policy.adapter_dry_run_plan import build_adapter_dry_run_plan_packet
from veritas_os.policy.adapter_dry_run_result import (
    build_adapter_dry_run_fixture_result_packet,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.bind_adapter_contract_selection import (
    verify_bind_adapter_contract_selection_packet,
)
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
    build_reference_adapter_in_memory_rehearsal_packet,
    verify_reference_adapter_in_memory_rehearsal_packet,
)


class FreshBindSourceChainError(ValueError):
    """Raised when the fresh source chain cannot preserve trusted identity."""


@dataclass(frozen=True)
class FreshBindSourceChainInputs:
    """Untrusted declarations consumed by existing production builders."""

    adapter_contract_selection_packet: Any
    fixture_step_results: Any
    reference_rehearsal_fixture: Any
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


@dataclass(frozen=True)
class FreshBindSourceChainResult:
    """Verified artifacts produced by one fresh, non-effecting composition."""

    root_rehearsal_packet: Any
    endpoint_packet: Any
    credential_packet: Any
    authority_linkage_packet: Any
    human_approval_linkage_packet: Any
    verified_gate_review_packet: Any


def _require_exact_intent(intent: ExecutionIntent, packet: Any, code: str) -> None:
    """Require exact object, identifier, and content-addressed hash equality."""
    if (
        packet.execution_intent != intent.to_dict()
        or packet.execution_intent_id != intent.execution_intent_id
        or packet.execution_intent_hash != hash_execution_intent(intent)
    ):
        raise FreshBindSourceChainError(code)


def build_fresh_bind_source_chain(
    execution_intent: ExecutionIntent,
    inputs: FreshBindSourceChainInputs,
    *,
    built_at: datetime,
) -> FreshBindSourceChainResult:
    """Construct and independently verify a new root and prerequisite chain.

    The caller cannot provide a root rehearsal packet.  An existing canonical
    adapter-contract selection is independently verified and required to carry
    the exact supplied intent; the production plan, fixture-result, and
    rehearsal builders then create a new content-addressed root.
    """
    selection = verify_bind_adapter_contract_selection_packet(
        inputs.adapter_contract_selection_packet
    )
    _require_exact_intent(
        execution_intent, selection, "FBS_SELECTION_EXECUTION_INTENT_MISMATCH"
    )
    plan = build_adapter_dry_run_plan_packet(selection, built_at)
    fixture_result = build_adapter_dry_run_fixture_result_packet(
        plan, inputs.fixture_step_results, built_at
    )
    root = build_reference_adapter_in_memory_rehearsal_packet(
        fixture_result, inputs.reference_rehearsal_fixture, built_at
    )
    root = verify_reference_adapter_in_memory_rehearsal_packet(root)
    _require_exact_intent(execution_intent, root, "FBS_ROOT_EXECUTION_INTENT_MISMATCH")

    readiness = build_live_adapter_dry_run_request_readiness_packet(root, built_at)
    request = build_live_adapter_dry_run_request_packet(readiness, built_at)
    dispatch = build_live_adapter_dry_run_dispatch_readiness_packet(request, built_at)
    endpoint = build_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
        dispatch,
        inputs.endpoint_candidate,
        inputs.endpoint_allowlist_snapshot,
        built_at,
    )
    credential = build_live_adapter_dry_run_credential_authorization_evaluation_packet(
        endpoint,
        inputs.credential_reference,
        inputs.credential_policy_snapshot,
        built_at,
    )
    operator = build_live_adapter_dry_run_operator_dispatch_review_packet(
        credential, inputs.operator_review_decision, built_at
    )
    pre_dispatch = build_live_adapter_dry_run_bind_pre_dispatch_review_packet(
        operator, inputs.bind_pre_dispatch_review_decision, built_at
    )
    authority = build_live_adapter_dry_run_authority_evidence_linkage_review_packet(
        pre_dispatch, inputs.authority_evidence_reference_bundle, built_at
    )
    human = build_live_adapter_dry_run_human_approval_linkage_review_packet(
        authority, inputs.human_approval_reference_bundle, built_at
    )
    final = build_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        human, inputs.final_readiness_review_decision, built_at
    )
    gate = build_live_adapter_dry_run_bind_authorization_gate_review_packet(
        final, inputs.gate_review_decision, built_at
    )
    verified = verify_live_adapter_dry_run_bind_authorization_gate_review_packet(gate)
    _require_exact_intent(
        execution_intent, verified, "FBS_FINAL_EXECUTION_INTENT_MISMATCH"
    )
    return FreshBindSourceChainResult(
        root_rehearsal_packet=root,
        endpoint_packet=endpoint,
        credential_packet=credential,
        authority_linkage_packet=authority,
        human_approval_linkage_packet=human,
        verified_gate_review_packet=verified,
    )


def fresh_bind_proof_report(
    result: FreshBindSourceChainResult,
) -> dict[str, bool]:
    """Derive source-chain claims without claiming issuance-only proofs."""
    gate = result.verified_gate_review_packet
    root = result.root_rehearsal_packet
    endpoint = result.endpoint_packet
    credential = result.credential_packet
    return {
        "decision_lineage_proven": (
            root.source_decision_identity["decision_id"]
            == root.execution_intent["decision_id"]
            and root.source_decision_identity["decision_hash"]
            == root.execution_intent["decision_hash"]
        ),
        "execution_intent_lineage_proven": (
            gate.execution_intent == root.execution_intent
            and gate.execution_intent_id == root.execution_intent_id
            and gate.execution_intent_hash == root.execution_intent_hash
        ),
        # Metadata linkage is not cryptographic Authority Evidence verification.
        "authority_evidence_proven": False,
        "revocation_checked": False,
        # Metadata linkage is not signed Human Approval verification.
        "human_approval_proven": False,
        "endpoint_binding_proven": bool(endpoint.allowlist_evaluation_result.matched),
        "adapter_contract_binding_proven": (
            endpoint.adapter_contract_id == root.adapter_contract_id
        ),
        "credential_reference_binding_proven": (
            credential.credential_reference["adapter_contract_id"]
            == root.adapter_contract_id
        ),
        "credential_scope_binding_proven": bool(
            credential.credential_authorization_result.authorized
        ),
        "authorization_source_chain_proven": bool(
            gate.bind_authorization_gate_review_result.accepted_for_future_real_bind_authorization_artifact
        ),
        # Issuance is performed only by the separate #2139 boundary.
        "real_bind_authorization_issued": False,
        "external_effect_performed": False,
        "real_decision_to_effect_e2e": False,
    }
