"""Negative and positive tests for the local Audit Evidence Chain Bridge v0.1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from scripts.validation.audit_evidence_chain_bridge import (
    serialize_bridge_report,
    verify_audit_evidence_chain_bridge,
)
from veritas_os.governance.evidence_chain_manifest import (
    build_evidence_chain_manifest,
    with_manifest_hash,
)
from veritas_os.governance.evidence_chain_verifier import verify_evidence_chain_manifest

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "tests/validation/fixtures/synthetic_example.json"
AT = "2026-10-31T00:00:00+00:00"
AUTH = "a" * 64
OUTCOME = "b" * 64
BIND = "c" * 64


def make_profile() -> dict:
    profile = json.loads(PROFILE_PATH.read_text())
    profile["scope"]["execution_performed"] = True
    case = profile["cases"][0]
    case.update({
        "expectation": "ALLOW",
        "observed": "PASS",
        "actual_effect": "ALLOWED",
        "decision_id": "decision-1",
        "intent_id": "intent-1",
        "authority_id": "authority-1",
        "bind_receipt_id": "bind-1",
        "effect_receipt_id": "outcome-1",
    })
    return profile


def make_manifest():
    return build_evidence_chain_manifest(
        decision_id="decision-1",
        execution_intent_id="intent-1",
        operation_id="operation-1",
        action_class="read_only",
        target_system="mock_saas",
        target_resource="synthetic:resource",
        requested_scope=["read"],
        final_outcome="commit",
        authority_evidence_id="authority-1",
        authority_evidence_hash=AUTH,
        bind_receipt_id="bind-1",
        bind_receipt_hash=BIND,
        outcome_receipt_id="outcome-1",
        outcome_receipt_hash=OUTCOME,
        bind_coverage_operation_id="operation-1",
        human_approval_required=False,
        generated_at=AT,
        metadata={"synthetic_fixture_only": True},
    )


def bridge(*, profile=None, manifest=None, **kwargs):
    options = {
        "profile": make_profile() if profile is None else profile,
        "profile_path": PROFILE_PATH,
        "case_id": "CASE-EXAMPLE",
        "manifest": make_manifest() if manifest is None else manifest,
        "authority_evidence": {"evidence_hash": AUTH},
        "outcome_receipt": {"outcome_hash": OUTCOME},
        "bind_receipt": {"receipt_hash": BIND},
        "bind_coverage_operation_id": "operation-1",
        "verified_at": AT,
    }
    options.update(kwargs)
    return verify_audit_evidence_chain_bridge(**options)


def test_link_verified_is_local_only_and_does_not_mutate_profile():
    profile = make_profile()
    original = deepcopy(profile)
    report = bridge(profile=profile)
    assert report["status"] == "LINK_VERIFIED", report
    assert report["source_verification_status"] == "verified"
    assert report["manifest_hash_matches"] is True
    assert report["synthetic_example"] is True
    assert all(x is True for x in report["identity_matches"].values() if x is not None)
    assert "not proof of an actual effect" in " ".join(report["claim_limitations"])
    assert profile == original


@pytest.mark.parametrize("profile_field", [
    "decision_id", "intent_id", "authority_id",
    "bind_receipt_id", "effect_receipt_id",
])
def test_identity_mismatch_is_failed(profile_field):
    profile = make_profile()
    profile["cases"][0][profile_field] = "wrong-id"
    result = bridge(profile=profile)
    assert result["status"] == "FAILED", (profile_field, result)
    assert "CHAIN_IDENTITY_MISMATCH" in result["failure_reasons"]


@pytest.mark.parametrize("profile_field", ["decision_id", "intent_id"])
def test_required_identity_missing_is_incomplete(profile_field):
    profile = make_profile()
    profile["cases"][0][profile_field] = None
    result = bridge(profile=profile)
    assert result["status"] == "INCOMPLETE"
    assert "CHAIN_IDENTITY_INCOMPLETE" in result["failure_reasons"]


def test_optional_identity_missing_in_manifest_is_incomplete():
    manifest = make_manifest()
    manifest = with_manifest_hash(replace(manifest, authority_evidence_id=None))
    result = bridge(manifest=manifest)
    assert result["status"] == "INCOMPLETE"


def test_source_mismatch_fails():
    result = bridge(authority_evidence={"evidence_hash": "f" * 64})
    assert result["status"] == "FAILED"
    assert result["source_verification_status"] == "failed"


def test_source_missing_evidence_remains_incomplete():
    result = bridge(authority_evidence=None)
    assert result["status"] == "INCOMPLETE"
    assert result["source_verification_status"] == "incomplete"


def test_source_indeterminate_remains_indeterminate():
    result = bridge(authority_evidence={})
    assert result["status"] == "INDETERMINATE"
    assert result["source_verification_status"] == "indeterminate"


def test_manifest_hash_mismatch_fails():
    result = bridge(manifest=replace(make_manifest(), manifest_hash="f" * 64))
    assert result["status"] == "FAILED"
    assert result["manifest_hash_matches"] is False


def test_unverified_source_state_cannot_be_elevated_by_complete_input():
    manifest = with_manifest_hash(replace(make_manifest(), chain_status="incomplete"))
    source = verify_evidence_chain_manifest(
        manifest=manifest,
        authority_evidence={"evidence_hash": AUTH},
        outcome_receipt={"outcome_hash": OUTCOME},
        bind_receipt={"receipt_hash": BIND},
        bind_coverage_operation_id="operation-1",
        verified_at=AT,
    )
    # The source verifier checks hashes, not the manifest's declared lifecycle.
    assert source.verification_status == "verified"
    result = bridge(manifest=manifest)
    assert result["status"] == "INCOMPLETE"
    assert "CHAIN_NOT_COMPLETE" in result["failure_reasons"]


def test_claimed_missing_manifest_links_are_not_elevated():
    manifest = with_manifest_hash(replace(make_manifest(), missing_links=["outcome_receipt_hash"]))
    result = bridge(manifest=manifest)
    assert result["status"] != "LINK_VERIFIED"


def test_unexecuted_profile_cannot_produce_positive_link():
    profile = make_profile()
    profile["scope"]["execution_performed"] = False
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "PROFILE_VALIDATION_FAILED" in result["failure_reasons"]


def test_unobserved_case_not_promoted():
    profile = make_profile()
    profile["cases"][0]["observed"] = "NOT_TESTED"
    profile["cases"][0]["actual_effect"] = "NOT_EXECUTED"
    result = bridge(profile=profile)
    assert result["status"] == "INCOMPLETE"
    assert "CASE_OUTCOME_UNOBSERVED" in result["failure_reasons"]


def test_case_without_local_evidence_not_promoted():
    profile = make_profile()
    profile["cases"][0]["evidence_ids"] = []
    result = bridge(profile=profile)
    assert result["status"] == "INCOMPLETE"


def test_case_missing_or_wrong_case_fails():
    result = bridge(case_id="CASE-NOT-THERE")
    assert result["status"] == "FAILED"


def test_duplicate_case_ids_are_rejected():
    profile = make_profile()
    profile["cases"].append(deepcopy(profile["cases"][0]))
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "DUPLICATE_CASE_ID" in result["failure_reasons"]


def test_serialized_self_asserted_verification_is_rejected():
    result = bridge(manifest={"manifest_id": "fake", "verification_status": "verified"})
    assert result["status"] == "FAILED"
    assert "UNTRUSTED_SERIALIZED_CHAIN_INPUT" in result["failure_reasons"]


def test_no_chain_manifest_is_not_link_verified():
    result = bridge(manifest={}, verified_at=AT)
    assert result["status"] == "FAILED"


def test_elevated_reviewer_claim_remains_rejected():
    profile = make_profile()
    profile["review"]["reviewer_verdict"] = "ACCEPT"
    profile["review"]["reviewer_independence"] = "EXTERNAL"
    profile["review"]["trusted_key_provenance"] = "ESTABLISHED"
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "PROFILE_VALIDATION_FAILED" in result["failure_reasons"]


def test_fake_handoff_remains_rejected():
    profile = make_profile()
    profile["review"]["handoff_status"] = "REVIEWABLE"
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"


def test_fake_authenticity_claim_remains_rejected():
    profile = make_profile()
    profile["evidence"][0]["authenticity_status"] = "VERIFIED"
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"


def test_local_evidence_digest_mismatch_fails():
    profile = make_profile()
    profile["evidence"][0]["sha256"] = "0" * 64
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "PROFILE_VALIDATION_FAILED" in result["failure_reasons"]


def test_serialization_deterministic_for_reordered_input_keys():
    profile = make_profile()
    first = bridge(profile=profile)
    reordered = {key: profile[key] for key in reversed(list(profile))}
    reordered["cases"] = [{key: value for key, value in reversed(list(profile["cases"][0].items()))}]
    second = bridge(profile=reordered)
    assert serialize_bridge_report(first) == serialize_bridge_report(second)
    assert json.loads(serialize_bridge_report(first)) == first


def test_operation_unbound_limitation_disclosed():
    report = bridge()
    assert "operation_id or manifest_id binding field" in " ".join(report["claim_limitations"])


def test_case_and_manifest_cannot_be_cross_bound():
    profile = make_profile()
    profile["cases"][0]["decision_id"] = "decision-other"
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
