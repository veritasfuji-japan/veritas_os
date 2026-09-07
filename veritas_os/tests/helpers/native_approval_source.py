"""Build native reference metadata from a real promotion, without effects.

Fixture helpers provide explicit local metadata only. All packet construction
and verification uses production code; no legacy handoff fields are fabricated.
"""

from datetime import timedelta

from veritas_os.policy.bind_adapter_contract_selection import (
    ADAPTER_METHODS,
    DESCRIPTOR_SCOPE_LIMITATIONS,
    EFFECT_PROFILE,
    PROHIBITED_DURING_SELECTION,
)
from veritas_os.policy.canonical_promotion_execution_intent_readiness import (
    build_canonical_promotion_execution_intent_readiness_packet as ready,
)
from veritas_os.policy.canonical_promotion_pre_bind_validation import (
    build_canonical_promotion_pre_bind_validation_packet as pre_bind,
)
from veritas_os.policy.canonical_promotion_bind_preflight_adjudication import (
    build_canonical_promotion_bind_preflight_adjudication_packet as preflight,
)
from veritas_os.policy.canonical_promotion_bind_adapter_contract_selection import (
    build_canonical_promotion_bind_adapter_contract_selection_packet as select,
)
from veritas_os.policy.canonical_promotion_adapter_dry_run_plan import (
    build_canonical_promotion_adapter_dry_run_plan_packet as plan,
)
from veritas_os.policy.canonical_promotion_adapter_dry_run_fixture_result import (
    build_canonical_promotion_adapter_dry_run_fixture_result_packet as fixture_result,
)
from veritas_os.policy.canonical_promotion_reference_adapter_rehearsal import (
    build_canonical_promotion_reference_adapter_in_memory_rehearsal_packet as rehearse,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_readiness import (
    build_canonical_promotion_live_adapter_dry_run_request_readiness_packet as request_ready,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_request import (
    build_canonical_promotion_live_adapter_dry_run_request_packet as request,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_dispatch_readiness import (
    build_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet as dispatch_ready,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_endpoint_allowlist import (
    build_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet as endpoint,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_credential_authorization import (
    build_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet as credential,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_operator_dispatch_review import (
    build_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet as operator,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review import (
    build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet as review,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet as authority,
)
from veritas_os.tests.test_canonical_promotion_adapter_dry_run_fixture_result import (
    _fixtures,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_endpoint_allowlist as endpoints,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_credential_authorization as credentials,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_operator_dispatch_review as operators,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review as reviews,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage as authorities,
)


def build_native_authority_source(promotion, now):
    """Preserve the actual API promotion through every native source stage."""
    intent = promotion.exact_execution_intent
    descriptor = {
        "adapter_contract_version": "bind-adapter-contract/v1",
        "adapter_kind": "reference",
        "adapter_name": "local-inert-declaration",
        "target_system": intent["target_system"],
        "target_resource_scope": intent["target_resource"],
        "supported_methods": list(ADAPTER_METHODS),
        "required_methods": list(ADAPTER_METHODS),
        "prohibited_during_selection": list(PROHIBITED_DURING_SELECTION),
        "effect_profile": EFFECT_PROFILE,
        "declared_by": "test:local",
        "declared_at": now.isoformat(),
        "descriptor_scope_limitations": list(DESCRIPTOR_SCOPE_LIMITATIONS),
    }
    selection = select(
        preflight(pre_bind(ready(promotion, checked_at=now), checked_at=now), now),
        descriptor,
        now,
    )
    planned = plan(selection, now)
    rehearsed = rehearse(
        fixture_result(planned, _fixtures(planned), now),
        {"scenario": "local-native-api"},
        now,
    )
    dispatch = dispatch_ready(request(request_ready(rehearsed, now), now), now)
    candidate = endpoints._candidate(
        adapter_contract_id=selection.adapter_contract_id,
        target_system=intent["target_system"],
        target_resource_scope=intent["target_resource"],
        declared_at=now.isoformat(),
    )
    allowed = endpoint(dispatch, candidate, endpoints._snapshot(candidate), now)
    reference = credentials._reference(
        adapter_contract_id=selection.adapter_contract_id,
        endpoint_candidate_id=candidate["endpoint_candidate_id"],
        target_system=intent["target_system"],
        target_resource_scope=intent["target_resource"],
        declared_at=now.isoformat(),
    )
    authorized_metadata = credential(
        allowed, reference, credentials._snapshot(reference), now
    )
    operator_decision = {
        **operators._decision(authorized_metadata),
        "reviewed_at": now.isoformat(),
    }
    reviewed = review(
        operator(authorized_metadata, operator_decision, now),
        {**reviews._decision(), "reviewed_at": now.isoformat()},
        now,
    )
    bundle = authorities._bundle(reviewed)
    bundle["bundle_declared_at"] = now.isoformat()
    for item in bundle["authority_evidence_references"]:
        item["authority_subject"] = intent["actor_identity"]
        item["authority_issued_at"] = (now - timedelta(seconds=1)).isoformat()
        item["authority_expires_at"] = (now + timedelta(minutes=5)).isoformat()
    return authority(reviewed, bundle, now)
