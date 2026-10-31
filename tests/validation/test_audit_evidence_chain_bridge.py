"""Negative and positive tests for the local Audit Evidence Chain Bridge v0.1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile

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
from veritas_os.security.hash import canonical_json_dumps, sha256_hex

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
    manifest_evidence = deepcopy(profile["evidence"][0])
    manifest_evidence["id"] = "EV-CHAIN"
    manifest_evidence["relative_path"] = "chain_manifest.json"
    manifest_evidence["notes"] = "Canonical local manifest bytes; synthetic only."
    profile["evidence"].append(manifest_evidence)
    case["evidence_ids"].append("EV-CHAIN")
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


def bridge(*, profile=None, manifest=None, binding_manifest=None, **kwargs):
    # The test uses a fresh isolated local evidence directory. A positive
    # link requires canonical on-disk manifest bytes in the cited profile item.
    supplied_profile = deepcopy(make_profile() if profile is None else profile)
    supplied_manifest = make_manifest() if manifest is None else manifest
    bound = (
        binding_manifest if binding_manifest is not None
        else supplied_manifest if hasattr(supplied_manifest, "to_dict")
        else make_manifest()
    )
    raw = canonical_json_dumps(bound.to_dict()).encode("utf-8")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        (temp / "sample_trace.txt").write_bytes(
            (ROOT / "tests/validation/fixtures/sample_trace.txt").read_bytes()
        )
        (temp / "chain_manifest.json").write_bytes(raw)
        for evidence in supplied_profile["evidence"]:
            if evidence["id"] == "EV-CHAIN":
                evidence["sha256"] = sha256_hex(raw)
        path = temp / "synthetic_example.json"
        path.write_text(json.dumps(supplied_profile))
        options = {
            "profile": supplied_profile,
            "profile_path": path,
            "case_id": "CASE-EXAMPLE",
            "manifest_evidence_id": "EV-CHAIN",
            "manifest": supplied_manifest,
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


def test_profile_local_manifest_sha_is_required():
    manifest = with_manifest_hash(replace(make_manifest(), operation_id="another-operation"))
    # The profile remains bound to the original manifest bytes.
    result = bridge(manifest=manifest, binding_manifest=make_manifest())
    assert result["status"] == "FAILED"
    assert "MANIFEST_EVIDENCE_DIGEST_MISMATCH" in result["failure_reasons"]


def test_manifest_evidence_is_explicit_and_case_local():
    assert bridge(manifest_evidence_id="")["status"] == "INCOMPLETE"
    result = bridge(manifest_evidence_id="EV-1")
    assert result["status"] == "FAILED"
    assert "MANIFEST_EVIDENCE_DIGEST_MISMATCH" in result["failure_reasons"]
    profile = make_profile()
    profile["cases"][0]["evidence_ids"].remove("EV-CHAIN")
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "MANIFEST_EVIDENCE_NOT_REFERENCED_BY_CASE" in result["failure_reasons"]


def test_named_bind_link_requires_hash_not_only_matching_id():
    manifest = with_manifest_hash(replace(make_manifest(), bind_receipt_hash=None))
    result = bridge(manifest=manifest)
    assert result["status"] == "INCOMPLETE"
    assert "NAMED_LINK_HASH_MISSING" in result["failure_reasons"]


def test_case_identity_tuple_must_be_unambiguous():
    profile = make_profile()
    other = deepcopy(profile["cases"][0])
    other["case_id"] = "CASE-OTHER"
    profile["cases"].append(other)
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "AMBIGUOUS_CASE_CHAIN_BINDING" in result["failure_reasons"]


def test_declared_commit_cannot_correspond_to_denied_effect():
    profile = make_profile()
    profile["cases"][0]["expectation"] = "DENY"
    profile["cases"][0]["actual_effect"] = "DENIED"
    result = bridge(profile=profile)
    assert result["status"] == "FAILED"
    assert "DECLARED_OUTCOME_CONTRADICTION" in result["failure_reasons"]


def test_manifest_required_approval_cannot_be_downgraded_by_default_bridge_flag():
    approval_hash = "d" * 64
    manifest = with_manifest_hash(replace(
        make_manifest(), human_approval_required=True,
        human_approval_receipt_hash=approval_hash,
        human_approval_receipt_id="approval-1",
    ))
    profile = make_profile()
    profile["cases"][0]["approval_id"] = "approval-1"
    supplied_receipt = {"receipt_hash": approval_hash}
    # Source verifier without the required approval flag would previously
    # accept these present hashes even without any verified approval proof.
    source_without_flag = verify_evidence_chain_manifest(
        manifest=manifest,
        authority_evidence={"evidence_hash": AUTH},
        human_approval_receipt=supplied_receipt,
        outcome_receipt={"outcome_hash": OUTCOME},
        bind_receipt={"receipt_hash": BIND},
        bind_coverage_operation_id="operation-1",
        approval_required=False,
        verified_at=AT,
    )
    assert source_without_flag.verification_status == "verified"
    result = bridge(
        profile=profile,
        manifest=manifest,
        human_approval_receipt=supplied_receipt,
        approval_required=False,
    )
    assert result["status"] == "INCOMPLETE", result
    assert result["source_verification_status"] == "incomplete"
    assert "human_approval_proof_hash_missing" in result["failure_reasons"]


def test_caller_required_approval_remains_fail_closed_when_manifest_does_not_require_it():
    result = bridge(approval_required=True)
    assert result["status"] == "INCOMPLETE", result
    assert "human_approval_proof_hash_missing" in result["failure_reasons"]


@pytest.mark.parametrize("outcome", ["blocked", "refused", "unknown"])
def test_complete_chain_cannot_claim_non_commit_final_outcome(outcome):
    manifest = with_manifest_hash(replace(make_manifest(), final_outcome=outcome))
    result = bridge(manifest=manifest)
    assert result["status"] == "FAILED", result
    assert "CHAIN_OUTCOME_STATUS_CONTRADICTION" in result["failure_reasons"]
