"""Tests for the Reviewer Evidence Packet v1 JSON Schema contract."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest


SCHEMA_PATH = Path("docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json")
FIXTURE_PATH = Path(
    "docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json"
)
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_TOP_LEVEL_FIELDS = [
    "packet_id",
    "packet_version",
    "demo_id",
    "generated_at",
    "title",
    "summary",
    "boundary_note",
    "local_offline_only",
    "cases",
    "aggregate_summary",
    "reviewer_notes",
    "packet_hash",
]
REQUIRED_CASE_FIELDS = [
    "case_id",
    "expected_outcome",
    "actual_outcome",
    "passed",
    "requested_scope",
    "target_system",
    "target_resource",
    "authority_validation_status",
    "runtime_recommended_outcome",
    "human_approval_summary",
    "refusal_basis",
    "failure_reasons",
    "outcome_receipt_summary",
    "evidence_chain_manifest_summary",
    "evidence_chain_verification_summary",
    "reviewer_interpretation",
    "boundary_note",
]
REQUIRED_HUMAN_APPROVAL_FIELDS = [
    "approved",
    "approval_receipt_id",
    "approver_identity",
    "approver_role",
    "approved_scope",
    "receipt_hash_present",
    "failure_reasons",
]
REQUIRED_OUTCOME_RECEIPT_FIELDS = [
    "outcome_receipt_id",
    "decision_id",
    "execution_intent_id",
    "operation_id",
    "action_class",
    "target_system",
    "target_resource",
    "intended_action",
    "requested_scope",
    "final_outcome",
    "committed",
    "blocked",
    "escalated",
    "rolled_back",
    "postcondition_status",
    "observed_effects",
    "failure_reasons",
    "evaluated_at",
    "outcome_hash",
    "metadata",
]
REQUIRED_MANIFEST_FIELDS = [
    "manifest_id",
    "decision_id",
    "execution_intent_id",
    "operation_id",
    "action_class",
    "target_system",
    "target_resource",
    "requested_scope",
    "authority_evidence_id",
    "authority_evidence_hash",
    "human_approval_receipt_id",
    "human_approval_receipt_hash",
    "bind_receipt_id",
    "bind_receipt_hash",
    "outcome_receipt_id",
    "outcome_receipt_hash",
    "bind_coverage_operation_id",
    "final_outcome",
    "chain_status",
    "missing_links",
    "refusal_basis",
    "observed_effects_summary",
    "generated_at",
    "manifest_hash",
    "metadata",
]
REQUIRED_VERIFICATION_FIELDS = [
    "is_valid",
    "verification_status",
    "manifest_id",
    "decision_id",
    "execution_intent_id",
    "operation_id",
    "verified_links",
    "missing_links",
    "mismatched_links",
    "failure_reasons",
    "recomputed_manifest_hash",
    "manifest_hash_matches",
    "verified_at",
    "metadata",
]
REQUIRED_AGGREGATE_FIELDS = [
    "total_cases",
    "passed_cases",
    "blocked_cases",
    "committed_cases",
    "verified_chains",
    "failed_chains",
    "incomplete_chains",
    "indeterminate_chains",
    "local_offline_only",
]

EVALUATION_GOVERNANCE_ARTIFACT = {
    "artifact_type": "root_authority_manifest",
    "artifact_ref": "docs/en/demo/fixtures/root-authority-manifest-v1.json",
    "artifact_hash": "0" * 64,
    "schema_ref": "docs/en/demo/schemas/root-authority-manifest-v1.schema.json",
    "required_for_review": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_reviewer_evidence_packet() -> dict[str, Any]:
    from scripts.demo.export_reviewer_evidence_packet import (
        build_reviewer_evidence_packet,
    )

    return build_reviewer_evidence_packet()


def _jsonschema_module() -> Any | None:
    if importlib.util.find_spec("jsonschema") is None:
        return None
    import jsonschema

    return jsonschema


def _assert_required_fields(payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    assert not missing, f"missing required fields: {missing}"


def _assert_string_array(value: Any) -> None:
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)


def _assert_nullable_hash(value: Any) -> None:
    assert value is None or SHA256_HEX_PATTERN.fullmatch(value)


def _assert_fallback_packet_shape(packet: dict[str, Any]) -> None:
    _assert_required_fields(packet, REQUIRED_TOP_LEVEL_FIELDS)
    assert packet["packet_id"] == "reviewer-evidence-packet-saas-permission-change-v1"
    assert packet["packet_version"] == "v1"
    assert packet["local_offline_only"] is True
    assert SHA256_HEX_PATTERN.fullmatch(packet["packet_hash"])
    assert isinstance(packet["reviewer_notes"], list)
    assert packet["reviewer_notes"]
    assert all(isinstance(note, str) and note for note in packet["reviewer_notes"])
    assert isinstance(packet["cases"], list)
    assert packet["cases"]
    for case in packet["cases"]:
        _assert_case_shape(case)
    _assert_aggregate_summary_shape(packet["aggregate_summary"])


def _assert_case_shape(case: dict[str, Any]) -> None:
    _assert_required_fields(case, REQUIRED_CASE_FIELDS)
    assert isinstance(case["case_id"], str)
    assert isinstance(case["expected_outcome"], str)
    assert case["actual_outcome"] in {
        "block",
        "commit",
        "commit_eligible",
        "refuse",
        "refused",
    }
    assert isinstance(case["passed"], bool)
    _assert_string_array(case["requested_scope"])
    _assert_string_array(case["refusal_basis"])
    _assert_string_array(case["failure_reasons"])
    assert isinstance(case["boundary_note"], str)
    _assert_human_approval_shape(case["human_approval_summary"])
    _assert_outcome_receipt_shape(case["outcome_receipt_summary"])
    _assert_manifest_shape(case["evidence_chain_manifest_summary"])
    _assert_verification_shape(case["evidence_chain_verification_summary"])


def _assert_human_approval_shape(summary: dict[str, Any]) -> None:
    _assert_required_fields(summary, REQUIRED_HUMAN_APPROVAL_FIELDS)
    assert isinstance(summary["approved"], bool)
    assert summary["approval_receipt_id"] is None or isinstance(
        summary["approval_receipt_id"], str
    )
    assert summary["approver_identity"] is None or isinstance(
        summary["approver_identity"], str
    )
    assert summary["approver_role"] is None or isinstance(summary["approver_role"], str)
    _assert_string_array(summary["approved_scope"])
    assert isinstance(summary["receipt_hash_present"], bool)
    _assert_string_array(summary["failure_reasons"])


def _assert_outcome_receipt_shape(summary: dict[str, Any]) -> None:
    _assert_required_fields(summary, REQUIRED_OUTCOME_RECEIPT_FIELDS)
    assert isinstance(summary["final_outcome"], str)
    assert isinstance(summary["committed"], bool)
    assert isinstance(summary["blocked"], bool)
    assert isinstance(summary["escalated"], bool)
    assert isinstance(summary["rolled_back"], bool)
    assert summary["postcondition_status"] in {
        "passed",
        "failed",
        "skipped",
        "indeterminate",
    }
    assert isinstance(summary["observed_effects"], list)
    _assert_string_array(summary["failure_reasons"])
    assert SHA256_HEX_PATTERN.fullmatch(summary["outcome_hash"])


def _assert_manifest_shape(summary: dict[str, Any]) -> None:
    _assert_required_fields(summary, REQUIRED_MANIFEST_FIELDS)
    assert summary["chain_status"] in {
        "complete",
        "incomplete",
        "blocked",
        "indeterminate",
    }
    _assert_nullable_hash(summary["authority_evidence_hash"])
    _assert_nullable_hash(summary["human_approval_receipt_hash"])
    _assert_nullable_hash(summary["bind_receipt_hash"])
    assert SHA256_HEX_PATTERN.fullmatch(summary["outcome_receipt_hash"])
    _assert_string_array(summary["missing_links"])
    _assert_string_array(summary["refusal_basis"])
    assert isinstance(summary["observed_effects_summary"], list)
    assert SHA256_HEX_PATTERN.fullmatch(summary["manifest_hash"])


def _assert_verification_shape(summary: dict[str, Any]) -> None:
    _assert_required_fields(summary, REQUIRED_VERIFICATION_FIELDS)
    assert isinstance(summary["is_valid"], bool)
    assert summary["verification_status"] in {
        "verified",
        "failed",
        "incomplete",
        "indeterminate",
    }
    assert isinstance(summary["manifest_hash_matches"], bool)
    _assert_string_array(summary["verified_links"])
    _assert_string_array(summary["missing_links"])
    _assert_string_array(summary["mismatched_links"])
    _assert_string_array(summary["failure_reasons"])
    _assert_nullable_hash(summary["recomputed_manifest_hash"])


def _assert_aggregate_summary_shape(summary: dict[str, Any]) -> None:
    _assert_required_fields(summary, REQUIRED_AGGREGATE_FIELDS)
    for field in REQUIRED_AGGREGATE_FIELDS[:-1]:
        assert isinstance(summary[field], int)
        assert summary[field] >= 0
    assert summary["local_offline_only"] is True


def _validate_or_fallback(packet: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        _assert_fallback_packet_shape(packet)
        return
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(packet)


def _is_rejected_or_fallback_detected(
    packet: dict[str, Any], schema: dict[str, Any]
) -> bool:
    try:
        _validate_or_fallback(packet, schema)
    except (AssertionError, Exception):
        return True
    return False


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.is_file()


def test_schema_file_parses_as_json() -> None:
    schema = _load_json(SCHEMA_PATH)
    assert isinstance(schema, dict)
    jsonschema = _jsonschema_module()
    if jsonschema is not None:
        jsonschema.Draft202012Validator.check_schema(schema)


def test_schema_declares_core_packet_properties() -> None:
    schema = _load_json(SCHEMA_PATH)
    for field in [
        "packet_id",
        "packet_version",
        "cases",
        "aggregate_summary",
        "packet_hash",
    ]:
        assert field in schema["required"]
        assert field in schema["properties"]


def test_golden_fixture_validates_against_schema_or_fallback() -> None:
    _validate_or_fallback(_load_json(FIXTURE_PATH), _load_json(SCHEMA_PATH))


def test_generated_packet_validates_against_schema_or_fallback() -> None:
    _validate_or_fallback(_build_reviewer_evidence_packet(), _load_json(SCHEMA_PATH))


def test_schema_requires_packet_hash() -> None:
    schema = _load_json(SCHEMA_PATH)
    assert "packet_hash" in schema["required"]


def test_schema_constrains_packet_hash_to_sha256_hex() -> None:
    schema = _load_json(SCHEMA_PATH)
    assert schema["$defs"]["sha256_hex"]["pattern"] == "^[0-9a-f]{64}$"


@pytest.mark.parametrize("packet_hash", ["", "A" * 64, "0" * 63, "g" * 64])
def test_schema_rejects_invalid_packet_hash(packet_hash: str) -> None:
    packet = _load_json(FIXTURE_PATH)
    packet["packet_hash"] = packet_hash
    assert _is_rejected_or_fallback_detected(packet, _load_json(SCHEMA_PATH))


def test_schema_constrains_packet_version_to_v1() -> None:
    schema = _load_json(SCHEMA_PATH)
    assert schema["properties"]["packet_version"] == {"const": "v1"}


def test_schema_constrains_local_offline_only_to_true() -> None:
    schema = _load_json(SCHEMA_PATH)
    assert schema["properties"]["local_offline_only"] == {"const": True}
    assert schema["$defs"]["aggregate_summary"]["properties"][
        "local_offline_only"
    ] == {"const": True}


@pytest.mark.parametrize(
    "field",
    [
        "outcome_receipt_summary",
        "evidence_chain_manifest_summary",
        "evidence_chain_verification_summary",
    ],
)
def test_schema_requires_nested_case_summaries(field: str) -> None:
    schema = _load_json(SCHEMA_PATH)
    assert field in schema["$defs"]["case"]["required"]


def test_schema_requires_aggregate_summary() -> None:
    schema = _load_json(SCHEMA_PATH)
    assert "aggregate_summary" in schema["required"]


def test_schema_rejects_or_fallback_detects_missing_packet_hash() -> None:
    packet = _load_json(FIXTURE_PATH)
    packet.pop("packet_hash")
    assert _is_rejected_or_fallback_detected(packet, _load_json(SCHEMA_PATH))


def test_schema_rejects_or_fallback_detects_invalid_packet_version() -> None:
    packet = _load_json(FIXTURE_PATH)
    packet["packet_version"] = "v2"
    assert _is_rejected_or_fallback_detected(packet, _load_json(SCHEMA_PATH))


@pytest.mark.parametrize(
    "field",
    [
        "outcome_receipt_summary",
        "evidence_chain_manifest_summary",
        "evidence_chain_verification_summary",
    ],
)
def test_schema_rejects_or_fallback_detects_missing_case_summary(field: str) -> None:
    packet = copy.deepcopy(_load_json(FIXTURE_PATH))
    packet["cases"][0].pop(field)
    assert _is_rejected_or_fallback_detected(packet, _load_json(SCHEMA_PATH))


def test_schema_validation_requires_no_network_or_environment_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _validate_or_fallback(_build_reviewer_evidence_packet(), _load_json(SCHEMA_PATH))


def test_schema_accepts_optional_evaluation_governance_artifacts() -> None:
    packet = copy.deepcopy(_load_json(FIXTURE_PATH))
    packet["evaluation_governance_artifacts"] = [
        EVALUATION_GOVERNANCE_ARTIFACT.copy()
    ]

    _validate_or_fallback(packet, _load_json(SCHEMA_PATH))


def test_evaluation_governance_artifacts_remain_optional() -> None:
    packet = _load_json(FIXTURE_PATH)

    assert "evaluation_governance_artifacts" not in packet
    _validate_or_fallback(packet, _load_json(SCHEMA_PATH))


def test_schema_rejects_invalid_evaluation_governance_artifact_type() -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        pytest.skip("jsonschema is unavailable")
    packet = copy.deepcopy(_load_json(FIXTURE_PATH))
    artifact = EVALUATION_GOVERNANCE_ARTIFACT.copy()
    artifact["artifact_type"] = "required_runtime_artifact"
    packet["evaluation_governance_artifacts"] = [artifact]

    validator = jsonschema.Draft202012Validator(_load_json(SCHEMA_PATH))
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(packet)


def test_schema_rejects_invalid_evaluation_governance_artifact_hash() -> None:
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        pytest.skip("jsonschema is unavailable")
    packet = copy.deepcopy(_load_json(FIXTURE_PATH))
    artifact = EVALUATION_GOVERNANCE_ARTIFACT.copy()
    artifact["artifact_hash"] = "not-a-sha256-hex"
    packet["evaluation_governance_artifacts"] = [artifact]

    validator = jsonschema.Draft202012Validator(_load_json(SCHEMA_PATH))
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(packet)
