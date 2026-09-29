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
    assert [item["id"] for item in gates] == [f"AER-{index:02d}" for index in range(1, 11)]
    status_by_id = {item["id"]: item["status"] for item in gates}
    assert status_by_id == {
        "AER-01": "PARTIAL",
        "AER-02": "PENDING_CI_PROOF",
        "AER-03": "NOT_DEFINED",
        "AER-04": "NOT_PROVEN",
        "AER-05": "NOT_PROVEN",
        "AER-06": "NOT_PROVEN",
        "AER-07": "NOT_GRANTED",
        "AER-08": "CURRENTLY_PROHIBITED_NOT_YET_ACTIVATION_PROVEN",
        "AER-09": "NOT_DEFINED",
        "AER-10": "NOT_AVAILABLE",
    }


def test_explicit_authorization_gate_cannot_be_satisfied_by_review_document() -> None:
    gate = next(item for item in _gate()["gates"] if item["id"] == "AER-07")
    assert gate["self_satisfied_by_this_review"] is False
    assert "separate explicit authorization/approval record" in gate["closure_condition"]


def test_closure_rule_forbids_activation_before_gate_closure() -> None:
    closure = _gate()["closure_rule"]
    assert closure["activation_can_occur_before_review_closure"] is False
    assert closure["effect_path_connection_can_be_authorized_by_this_gate"] is False
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
