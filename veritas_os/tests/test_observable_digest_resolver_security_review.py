"""Contract tests for observable-digest resolver security-review freeze."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "security" / "observable_digest_resolver_security_review_v1.json"
DOC_PATH = ROOT / "docs" / "en" / "security" / "observable-digest-resolver-security-review-v1.md"


def _matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_security_review_keeps_behavior_blocked() -> None:
    matrix = _matrix()
    assert matrix["review_status"] == "PRE_BEHAVIOR_BLOCKED"
    assert matrix["behavior_authorized"] is False
    assert matrix["activation_gate"]["state"] == "BLOCKED"


def test_security_review_preserves_contract_non_amplification_invariants() -> None:
    matrix = _matrix()
    assert matrix["hard_invariant"] == {
        "authority_created": False,
        "execution_permission_changed": False,
        "digest_match_asserted": False,
        "boundary_validation_asserted": False,
        "uncertainty_erased": False,
        "remediation_executed": False,
    }


def test_mark_adversarial_paths_are_explicitly_covered() -> None:
    matrix = _matrix()
    categories = {item["category"] for item in matrix["threats"]}
    assert {
        "REDIRECTS",
        "RETRIES",
        "FALLBACKS",
        "CACHED_EVIDENCE",
        "DNS_CHANGES_AND_REBINDING",
        "CREDENTIALS",
        "STALE_RESULTS_AND_TIME",
        "PARTIAL_FAILURES",
        "AMBIGUOUS_ERRORS",
    }.issubset(categories)


def test_ssrf_and_network_boundary_are_frozen_before_behavior() -> None:
    matrix = _matrix()
    categories = {item["category"] for item in matrix["threats"]}
    assert {
        "SCHEME_ALLOWLIST_AND_SSRF",
        "NETWORK_EGRESS",
        "TENANT_AND_SCOPE_ISOLATION",
        "TRANSPORT_TRUST_AND_AUTHENTICITY",
    }.issubset(categories)


def test_all_threats_have_controls_negative_tests_and_unimplemented_status() -> None:
    matrix = _matrix()
    threats = matrix["threats"]
    assert len(threats) == 16
    assert len({item["id"] for item in threats}) == len(threats)
    for item in threats:
        assert item["status"] == "REQUIRED_NOT_IMPLEMENTED"
        assert item["risk"]
        assert item["required_controls"]
        assert item["required_negative_tests"]


def test_redirect_controls_forbid_silent_authority_widening() -> None:
    matrix = _matrix()
    redirect = next(item for item in matrix["threats"] if item["category"] == "REDIRECTS")
    controls = "\n".join(redirect["required_controls"])
    assert "disabled by default" in controls
    assert "every hop" in controls
    assert "Do not forward credentials" in controls


def test_retry_and_cache_controls_preserve_historical_uncertainty() -> None:
    matrix = _matrix()
    by_category = {item["category"]: item for item in matrix["threats"]}
    retry_controls = "\n".join(by_category["RETRIES"]["required_controls"])
    cache_controls = "\n".join(by_category["CACHED_EVIDENCE"]["required_controls"])
    assert "later success must not erase" in retry_controls
    assert "cannot erase a prior unresolved state" in cache_controls


def test_credentials_cannot_alias_execution_credentials() -> None:
    matrix = _matrix()
    credentials = next(item for item in matrix["threats"] if item["category"] == "CREDENTIALS")
    controls = "\n".join(credentials["required_controls"])
    assert "distinct from execution credentials" in controls
    assert "never appear in result" in controls


def test_security_document_states_non_claims_and_hard_invariant() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "hard invariant" in text
    assert "Resolver behavior remains **BLOCKED**" in text
    assert "The answer must remain **yes under adversarial conditions**" in text
    assert "does not establish" in text
    assert "production security" in text


def test_cross_cutting_paths_are_frozen_before_behavior() -> None:
    matrix = _matrix()
    paths = matrix["cross_cutting_paths"]
    assert len(paths) == 7
    assert [item["category"] for item in paths] == [
        "CANONICALIZATION_AND_PARSER_DIFFERENTIALS",
        "CONFUSED_DEPUTY_AND_AUTHORITY_PROVENANCE",
        "TIME_OF_CHECK_TIME_OF_USE",
        "NONDETERMINISTIC_RESOLUTION",
        "RESOURCE_EXHAUSTION_AMPLIFICATION",
        "SUPPLY_CHAIN_AND_TRUST_ROOT_SUBSTITUTION",
        "EVIDENCE_INTEGRITY_AND_AUDIT_ORDERING_TAMPERING",
    ]
    for item in paths:
        assert item["status"] == "REQUIRED_NOT_IMPLEMENTED"
        assert item["required_controls"]
        assert item["required_negative_tests"]


def test_proof_obligations_cover_what_when_authority_and_forbidden_inference() -> None:
    matrix = _matrix()
    obligations = matrix["proof_obligations"]
    assert set(obligations) == {
        "what_was_observed",
        "when_it_was_observed",
        "under_which_access_authority",
        "forbidden_inferences",
    }
    for item in obligations.values():
        assert item["required"] is True
        assert item["description"]


def test_composition_rule_forbids_unauthorized_conclusion_amplification() -> None:
    matrix = _matrix()
    assert "No combination of individually permitted mechanisms" in matrix["composition_rule"]
    assert "Authority" in matrix["composition_rule"]
    assert "execution permission" in matrix["composition_rule"]


def test_composite_adversarial_scenarios_are_frozen() -> None:
    matrix = _matrix()
    scenarios = matrix["composite_adversarial_tests"]
    assert len(scenarios) == 10
    assert len({item["id"] for item in scenarios}) == 10
    for item in scenarios:
        assert item["paths"]
        assert item["scenario"]
        assert item["required_outcome"] in {
            "BLOCKED_OR_UNRESOLVED",
            "UNRESOLVED",
            "UNCERTAINTY_PRESERVED",
            "CONFLICT_VISIBLE_OR_UNRESOLVED",
            "HISTORY_NOT_PROVABLE",
        }
        assert item["invariant"]


def test_composite_suite_covers_key_cross_control_combinations() -> None:
    matrix = _matrix()
    joined = "\n".join(
        " ".join(item["paths"]) for item in matrix["composite_adversarial_tests"]
    )
    for required in [
        "REDIRECTS",
        "DNS_CHANGES_AND_REBINDING",
        "CREDENTIALS",
        "RETRIES",
        "CACHED_EVIDENCE",
        "TIME_OF_CHECK_TIME_OF_USE",
        "CANONICALIZATION_AND_PARSER_DIFFERENTIALS",
        "RESOURCE_EXHAUSTION_AMPLIFICATION",
        "SUPPLY_CHAIN_AND_TRUST_ROOT_SUBSTITUTION",
        "EVIDENCE_INTEGRITY_AND_AUDIT_ORDERING_TAMPERING",
    ]:
        assert required in joined


def test_activation_gate_requires_cross_cutting_and_composite_evidence() -> None:
    matrix = _matrix()
    requirements = "\n".join(matrix["activation_gate"]["requirements"])
    assert "seven cross-cutting adversarial paths" in requirements
    assert "Composite adversarial tests" in requirements
    assert "what was observed" in requirements
    assert "under which bounded read-access authority" in requirements


def test_security_document_freezes_cross_cutting_and_composition_review() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "7 cross-cutting adversarial paths" in text
    assert "Canonicalization and parser differentials" in text
    assert "Confused deputy and authority provenance" in text
    assert "Time-of-check / time-of-use" in text
    assert "Nondeterministic resolution" in text
    assert "Supply-chain and trust-root substitution" in text
    assert "Evidence integrity and audit ordering tampering" in text
    assert "Required proof obligations" in text
    assert "Composition rule" in text
    assert "No combination of individually permitted mechanisms" in text
