"""Regression tests for the observable-digest resolver activation evidence gate."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "security" / "observable_digest_resolver_activation_evidence_review_v1.json"
DOC_PATH = ROOT / "docs" / "en" / "security" / "observable-digest-resolver-activation-evidence-review-v1.md"
RESOLVER_PATH = ROOT / "veritas_os" / "audit" / "observable_digest_resolver.py"


def _gate() -> dict[str, object]:
    return json.loads(GATE_PATH.read_text(encoding="utf-8"))


def test_activation_review_is_open_and_cannot_self_authorize() -> None:
    gate = _gate()
    assert gate["status"] == "ACTIVATION_EVIDENCE_REVIEW_OPEN"
    assert gate["activation_authorized"] is False
    assert gate["activation_approved"] is False
    assert gate["activation_performed"] is False
    assert gate["effect_path_connection_authorized"] is False
    assert gate["self_authorization_allowed"] is False


def test_validated_identity_and_missing_exact_merge_rerun_remain_explicit() -> None:
    baseline = _gate()["baseline"]
    assert baseline["implementation_merge_sha"] == "f3db837d8233afbb998195890525fcbe511c2f2c"
    assert baseline["validated_pr_head_sha"] == "0fe3e95364fe9c7abdd3e58e5ec3f861935123ff"
    assert baseline["merge_file_identical_to_validated_head"] is True
    assert baseline["exact_merge_sha_ci_rerun_observed"] is False
    assert baseline["implementation_review_scope"] == "IMPLEMENTATION_REVIEW_ONLY"


def test_activation_target_is_evidence_only_and_effect_path_is_forbidden() -> None:
    target = _gate()["activation_target_boundary"]
    assert target["target_id"] == "RESOLVER_EVIDENCE_ONLY_ACTIVATION_V1"
    assert target["permitted_profile"] == "separate_store_readonly_v1"
    assert target["permitted_result_role"] == "EVIDENCE_ONLY"
    assert target["direct_effect_path_use"] is False
    assert target["direct_policy_allow_use"] is False
    assert target["direct_bind_authorization_use"] is False
    assert target["direct_execution_permission_use"] is False
    assert target["default_state"] == "DISABLED"


def test_all_activation_gates_are_present_and_not_falsely_closed() -> None:
    gates = _gate()["gates"]
    assert [item["id"] for item in gates] == [f"AER-{index:02d}" for index in range(1, 12)]
    status_by_id = {item["id"]: item["status"] for item in gates}
    assert status_by_id == {
        "AER-01": "CLOSED_PASS",
        "AER-02": "PROOF_PENDING_EXACT_MAIN",
        "AER-03": "NOT_DEFINED",
        "AER-04": "NOT_PROVEN",
        "AER-05": "NOT_PROVEN",
        "AER-06": "NOT_PROVEN",
        "AER-07": "NOT_GRANTED",
        "AER-08": "CURRENTLY_PROHIBITED_NOT_YET_ACTIVATION_PROVEN",
        "AER-09": "NOT_DEFINED",
        "AER-10": "NOT_AVAILABLE",
        "AER-11": "NOT_DEFINED",
    }


def test_explicit_authorization_gate_cannot_be_satisfied_by_review_document() -> None:
    gate = next(item for item in _gate()["gates"] if item["id"] == "AER-07")
    assert gate["self_satisfied_by_this_review"] is False
    assert "separate explicit authorization/approval record" in gate["closure_condition"]


def test_closure_rule_forbids_activation_before_gate_closure() -> None:
    closure = _gate()["closure_rule"]
    assert closure["activation_can_occur_before_review_closure"] is False
    assert closure["effect_path_connection_can_be_authorized_by_this_gate"] is False
    assert closure["independent_review_required_before_activation"] is True
    assert closure["independent_review_cannot_substitute_for_authorization"] is True
    assert closure["authorization_cannot_substitute_for_independent_review"] is True
    assert closure["material_change_reopens_review"] is True


def test_current_production_source_has_no_resolver_import_or_call_path() -> None:
    forbidden = (
        "resolve_separate_store_readonly_v1",
        "SeparateStoreReadonlyProfile",
        "observable_digest_resolver",
    )
    violations: list[str] = []
    production_root = ROOT / "veritas_os"

    for path in sorted(production_root.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if path == RESOLVER_PATH:
            continue
        if "tests" in relative.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            violations.append(str(relative))

    assert violations == [], f"undeclared resolver production reachability: {violations}"


def test_activation_review_document_preserves_non_authorization_boundary() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "ACTIVATION_EVIDENCE_REVIEW_OPEN" in text
    assert "ACTIVATION NOT JUSTIFIED" in text
    assert "does **not** authorize activation" in text
    assert "This activation gate can never authorize an effect-path connection." in text
    assert "The activation-review document itself can never authorize activation." in text


def test_completeness_review_adds_independent_challenge_without_activation_approval() -> None:
    review = _gate()["completeness_review"]
    assert review["review_scope"] == "ACTIVATION_EVIDENCE_GATE_COMPLETENESS_ONLY"
    assert review["ten_gate_outcome"] == "ESSENTIAL_BOUNDARIES_CAPTURED"
    assert review["additional_category_requested"] == "INDEPENDENT_CHALLENGE_AND_AUDITABILITY"
    assert review["activation_approval_granted"] is False
    assert review["effect_path_connection_permission_granted"] is False


def test_aer11_requires_reviewer_separation_and_auditable_decision() -> None:
    gate = next(item for item in _gate()["gates"] if item["id"] == "AER-11")
    assert gate["name"] == "INDEPENDENT_CHALLENGE_AND_AUDITABILITY"
    assert gate["status"] == "NOT_DEFINED"

    separation = gate["reviewer_separation"]
    assert separation["implementation_author_may_be_independent_reviewer"] is False
    assert separation["activation_requester_may_be_independent_reviewer"] is False
    assert separation["authorization_approver_may_automatically_substitute_for_independent_reviewer"] is False

    decisions = gate["decision_semantics"]
    assert decisions["allowed_decisions"] == ["APPROVE", "REFUSE", "ABSTAIN"]
    assert decisions["missing_decision_blocks_activation"] is True
    assert decisions["refuse_blocks_activation"] is True
    assert decisions["abstain_blocks_activation"] is True
    assert decisions["unresolved_finding_blocks_activation"] is True
    assert decisions["approval_does_not_create_execution_authority"] is True
    assert decisions["approval_does_not_authorize_effect_path_connection"] is True


def test_aer11_freezes_minimum_review_artifact_manifest() -> None:
    gate = next(item for item in _gate()["gates"] if item["id"] == "AER-11")
    artifacts = gate["minimum_review_artifacts"]
    required = {
        "exact implementation identity and code/test artifact identities",
        "AER-01 through AER-09 status/evidence package",
        "exact proposed activation target, caller, profile, namespace and configuration",
        "snapshot provenance/admissibility evidence",
        "consumer non-amplification evidence",
        "failure/uncertainty propagation evidence",
        "explicit authorization/approval record from AER-07",
        "effect-path separation evidence",
        "default-disabled enable/disable/rollback evidence",
        "all open findings, limitations and non-claims",
    }
    assert set(artifacts) == required


def test_activation_review_document_freezes_independent_challenge_boundary() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "Gate AER-11 — Independent challenge and auditability" in text
    assert "Explicit Authorization / Approval" in text
    assert "!= Independent Challenge / Auditability" in text
    assert "APPROVE" in text
    assert "REFUSE" in text
    assert "ABSTAIN" in text
    assert "AER-11 must close before activation." in text


def test_aer01_exact_identity_proof_plan_is_frozen_and_non_authorizing() -> None:
    gate = next(item for item in _gate()["gates"] if item["id"] == "AER-01")
    plan = gate["proof_plan"]
    assert gate["status"] == "CLOSED_PASS"
    assert plan["rule_of_one"] == "AER-01_EXACT_IMPLEMENTATION_IDENTITY_V1"
    assert plan["expected_runtime_blob_sha"] == "64431fecf69579d8554cbc590a67ce8ca9d4a612"
    assert plan["expected_behavior_test_blob_sha"] == "a247bf768ca7a0ac6f65ac13fbb2e07664336b30"
    assert plan["expected_implementation_manifest_blob_sha"] == "5174dab99f9284498966a4bd8968db5ec910b052"
    assert plan["exact_main_run_required"] is True
    assert plan["independent_closure_record_required"] is True
    assert plan["activation_authorized_by_proof"] is False
    assert plan["activation_approved_by_proof"] is False


def test_aer01_closure_is_pinned_to_exact_main_evidence() -> None:
    gate = next(item for item in _gate()["gates"] if item["id"] == "AER-01")
    closure = gate["closure_record"]
    assert closure["determination"] == "CLOSED_PASS"
    assert closure["exact_merged_main_sha"] == "94faafa1a42fde18a3cf03c41e54e731266e82fb"
    assert closure["workflow_run_id"] == 37208356216
    assert closure["workflow_run_event"] == "push"
    assert closure["workflow_run_conclusion"] == "success"
    assert closure["job_id"] == 111454223084
    assert closure["artifact_id"] == 11305563535
    assert closure["artifact_sha256"] == "8103465d432ef2470a887dacca70c5a76d88561ba18c5c9b090735c89ed8f989"
    assert closure["expected_and_observed_blob_identities_match"] is True
    assert closure["activation_authorized"] is False
    assert closure["activation_approved"] is False
    assert closure["activation_performed"] is False
    assert closure["effect_path_connection_authorized"] is False
    assert gate["missing_evidence"] == []
