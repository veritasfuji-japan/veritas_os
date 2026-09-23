"""Contract tests for the minimal observable-digest resolver behavior proposal."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROPOSAL_PATH = ROOT / "security" / "observable_digest_resolver_minimal_behavior_proposal_v1.json"
DOC_PATH = ROOT / "docs" / "en" / "architecture" / "observable-digest-resolver-minimal-behavior-proposal-v1.md"


def _proposal() -> dict[str, object]:
    return json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))


def test_proposal_is_non_behavioral_and_blocked() -> None:
    proposal = _proposal()
    assert proposal["status"] == "PROPOSAL_ONLY"
    assert proposal["behavior_implemented"] is False
    assert proposal["behavior_authorized"] is False
    assert proposal["activation_gate"] == "BLOCKED"


def test_initial_profile_is_single_non_network_read_only_profile() -> None:
    profile = _proposal()["proposed_initial_profile"]
    assert profile["profile_id"] == "separate_store_readonly_v1"
    assert profile["supported_scheme"] == "separate_store"
    data_source = profile["data_source"]
    assert data_source["network_access"] is False
    assert data_source["filesystem_access"] is False
    assert data_source["database_access"] is False
    assert data_source["object_store_access"] is False
    assert data_source["environment_lookup"] is False
    assert data_source["ambient_credentials"] is False
    assert data_source["mutable_shared_state"] is False


def test_initial_profile_has_no_retry_redirect_cache_fallback_or_decide_wiring() -> None:
    behavior = _proposal()["proposed_initial_profile"]["behavior"]
    for key in [
        "redirects",
        "dns",
        "retries",
        "fallbacks",
        "cache",
        "network_egress",
        "credential_lookup",
        "automatic_invocation",
        "decide_route_wiring",
    ]:
        assert behavior[key] is False


def test_locator_grammar_is_fail_closed_and_non_normalizing() -> None:
    rules = _proposal()["proposed_initial_profile"]["locator_rules"]
    assert rules["ascii_only"] is True
    assert rules["percent_encoding_allowed"] is False
    assert rules["query_allowed"] is False
    assert rules["fragment_allowed"] is False
    assert rules["userinfo_allowed"] is False
    assert rules["empty_segments_allowed"] is False
    assert rules["dot_segments_allowed"] is False
    assert rules["max_locator_length"] == 500


def test_access_model_separates_read_scope_from_execution_authority() -> None:
    access = _proposal()["proposed_initial_profile"]["access_model"]
    assert access["credential_bearing"] is False
    assert access["caller_allowlist_required"] is True
    assert access["namespace_scope_pinned_in_profile"] is True
    assert access["cross_namespace_access"] is False
    assert access["resolver_service_privilege_escalation"] is False
    assert access["execution_authority_created"] is False


def test_failure_mapping_keeps_unknown_transient_out_of_pure_snapshot_profile() -> None:
    mapping = _proposal()["proposed_failure_mapping"]
    assert "LOCATOR_MISSING" in mapping
    assert "LOCATOR_MALFORMED" in mapping
    assert "AUTHZ_DENIED" in mapping
    assert "RESOLUTION_FAILED" in mapping
    assert "SCHEMA_MISMATCH" in mapping
    assert "not emitted" in mapping["UNKNOWN_TRANSIENT"]


def test_monotonicity_and_fail_closed_rules_are_frozen() -> None:
    invariants = _proposal()["governing_invariants"]
    assert invariants["evidence_degradation_never_increases_conclusion_authority"] is True
    assert invariants["fail_closed_when_evidence_chain_no_longer_justifies_requested_conclusion"] is True


def test_four_proof_obligations_remain_explicit() -> None:
    obligations = _proposal()["proof_obligations"]
    assert set(obligations) == {
        "what_was_observed",
        "when_it_was_observed",
        "under_which_bounded_read_access_authority",
        "forbidden_inferences",
    }
    assert "execution permission" in obligations["forbidden_inferences"]
    assert "digest match" in obligations["forbidden_inferences"]


def test_behavior_implementation_must_be_separate_and_unwired() -> None:
    requirements = "\n".join(_proposal()["activation_requirements"])
    assert "separate PR" in requirements
    assert "unwired from /v1/decide" in requirements
    assert "reopens security review" in requirements


def test_document_preserves_proposal_only_claim_boundary() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "**Proposal only.**" in text
    assert "**Activation gate:** **BLOCKED**." in text
    assert "evidence degradation" in text
    assert "must never increase conclusion authority" in text
    assert "separate_store_readonly_v1" in text
    assert "No resolver runtime" not in text  # exact wording intentionally not used
    assert "This proposal does not authorize behavior." in text
