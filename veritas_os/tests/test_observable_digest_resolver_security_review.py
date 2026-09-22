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
