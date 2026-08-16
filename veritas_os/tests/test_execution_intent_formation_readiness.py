"""Security tests for ExecutionIntent Formation Readiness v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.execution_intent_formation_readiness import (
    EXECUTION_INTENT_REQUIRED_FIELDS,
    MAPPING_DOMAIN,
    REQUIRED_FIELD_PRESENCE,
    SCOPE_LIMITATIONS,
    CanonicalExecutionIntentFormationReadinessPacket,
    ExecutionIntentFormationReadinessError,
    _digest,
    _packet_hash,
    build_execution_intent_formation_readiness_packet,
    verify_execution_intent_formation_readiness_packet,
)
from veritas_os.policy.guarded_promotion_eligibility import (
    PACKET_DOMAIN as ELIGIBILITY_PACKET_DOMAIN,
    _digest as eligibility_digest,
    build_guarded_promotion_eligibility_packet,
)
from veritas_os.tests.test_canonical_decision_handoff import _complete_context

VECTOR = Path(
    "docs/en/architecture/test-vectors/decision-to-bind-handoff-v1/vector-01.json"
)
NOW = datetime(2030, 1, 1, 0, 0, 3, tzinfo=timezone.utc)


def _eligibility():
    handoff = json.loads(VECTOR.read_text())["input"]
    return build_guarded_promotion_eligibility_packet(
        handoff, _complete_context(handoff), NOW, NOW
    )


def _canonical_replay_eligibility(*, semantic_match: bool, fields_changed: list[str]):
    """Build eligibility with explicit, distinct canonical replay identities."""
    handoff = json.loads(VECTOR.read_text())["input"]
    handoff["replay_lineage"].update(
        original_request_id="original-request-001",
        replay_request_id="replay-request-001",
        original_decision_id="cda:v1:sha256:" + "a" * 64,
        replay_decision_id="cda:v1:sha256:" + "b" * 64,
        semantic_profile="veritas.replay-semantic/v1",
        semantic_match=semantic_match,
        fields_changed=fields_changed,
        severity="info" if semantic_match else "warning",
        divergence_level=(
            "no_divergence" if semantic_match else "acceptable_divergence"
        ),
    )
    replay_record = next(
        item for item in handoff["provenance"] if item["field_path"] == "replay_lineage"
    )
    replay_record["value"] = deepcopy(handoff["replay_lineage"])
    return build_guarded_promotion_eligibility_packet(
        handoff, _complete_context(handoff), NOW, NOW
    )


def _packet():
    return build_execution_intent_formation_readiness_packet(_eligibility(), NOW)


def _resign(raw: dict) -> dict:
    raw["readiness_hash"] = _packet_hash(raw)
    raw["readiness_id"] = f"eifr:v1:sha256:{raw['readiness_hash']}"
    return raw


def _resign_eligibility(raw: dict) -> dict:
    preimage = {
        key: value
        for key, value in raw.items()
        if key not in {"eligibility_id", "eligibility_hash"}
    }
    raw["eligibility_hash"] = eligibility_digest(ELIGIBILITY_PACKET_DOMAIN, preimage)
    raw["eligibility_id"] = f"gpe:v1:sha256:{raw['eligibility_hash']}"
    return raw


def test_build_verify_mapping_and_content_addressing() -> None:
    eligibility = _eligibility()
    packet = build_execution_intent_formation_readiness_packet(eligibility, NOW)
    assert verify_execution_intent_formation_readiness_packet(packet) == packet
    assert packet.readiness_id == f"eifr:v1:sha256:{packet.readiness_hash}"
    assert packet.readiness_hash == _packet_hash(packet.model_dump(mode="json"))
    evidence = eligibility.evidence_lineage
    assert packet.source_to_execution_intent_mapping == {
        "decision_id": eligibility.source_decision_identity["canonical_decision_id"],
        "request_id": eligibility.source_decision_identity["request_id"],
        "policy_snapshot_id": evidence["policy_snapshot_id"],
        "actor_identity": eligibility.candidate_identity["actor_identity"],
        "target_system": eligibility.candidate_identity["target_system"],
        "target_resource": eligibility.candidate_identity["target_resource"],
        "intended_action": eligibility.candidate_identity["action_contract_id"],
        "evidence_refs": [
            evidence["trustlog_artifact_ref"],
            evidence["replay_artifact_ref"],
            evidence["authority_evidence_ref"],
            evidence["human_approval_receipt_ref"],
            evidence["expected_state_source_ref"],
        ],
        "decision_hash": eligibility.source_decision_identity[
            "canonical_decision_hash"
        ],
        "decision_ts": eligibility.source_decision_identity["canonical_decision_ts"],
        "ttl_seconds": None,
        "expected_state_fingerprint": evidence["expected_state_fingerprint"],
        "approval_context": {
            "human_approval_receipt_ref": evidence["human_approval_receipt_ref"],
            "human_approval_receipt_hash": evidence["human_approval_receipt_hash"],
        },
        "policy_lineage": {
            "policy_snapshot_id": evidence["policy_snapshot_id"],
            "policy_version": evidence["policy_version"],
            "policy_semantic_digest": evidence["policy_semantic_digest"],
        },
    }
    assert packet.mapping_value_digest == _digest(
        MAPPING_DOMAIN, packet.source_to_execution_intent_mapping
    )
    assert packet.execution_intent_required_fields == (EXECUTION_INTENT_REQUIRED_FIELDS)
    assert packet.required_field_presence == REQUIRED_FIELD_PRESENCE
    assert packet.scope_limitations == SCOPE_LIMITATIONS


def test_source_summaries_and_replay_identity_are_preserved() -> None:
    eligibility = _eligibility()
    packet = _packet()
    assert packet.source_decision_identity == eligibility.source_decision_identity
    assert packet.candidate_identity == eligibility.candidate_identity
    assert packet.evidence_lineage == eligibility.evidence_lineage
    assert packet.replay_summary == eligibility.replay_summary
    original_request_id = packet.replay_summary.get("original_request_id")
    replay_request_id = packet.replay_summary.get("replay_request_id")
    if original_request_id is not None and replay_request_id is not None:
        assert original_request_id != replay_request_id
    original_decision_id = packet.replay_summary.get("original_decision_id")
    replay_decision_id = packet.replay_summary.get("replay_decision_id")
    if original_decision_id is not None and replay_decision_id is not None:
        assert original_decision_id != replay_decision_id


def test_explicit_canonical_replay_identities_are_preserved() -> None:
    eligibility = _canonical_replay_eligibility(semantic_match=True, fields_changed=[])
    packet = build_execution_intent_formation_readiness_packet(eligibility, NOW)
    assert packet.replay_summary["original_request_id"] == "original-request-001"
    assert packet.replay_summary["replay_request_id"] == "replay-request-001"
    assert (
        packet.replay_summary["original_request_id"]
        != packet.replay_summary["replay_request_id"]
    )
    assert (
        packet.replay_summary["original_decision_id"]
        != packet.replay_summary["replay_decision_id"]
    )
    assert packet.replay_summary["semantic_match"] is True
    assert packet.replay_summary["fields_changed"] == []


@pytest.mark.parametrize(
    "semantic_match,fields_changed",
    [(True, []), (False, ["outcome.status"])],
)
def test_semantic_match_is_preserved_not_gated(
    semantic_match: bool, fields_changed: list[str]
) -> None:
    eligibility = _canonical_replay_eligibility(
        semantic_match=semantic_match, fields_changed=fields_changed
    )
    packet = build_execution_intent_formation_readiness_packet(eligibility, NOW)
    assert packet.replay_summary["semantic_match"] is semantic_match
    assert packet.replay_summary["fields_changed"] == fields_changed
    assert verify_execution_intent_formation_readiness_packet(packet) == packet


def test_legacy_absent_semantic_match_is_preserved() -> None:
    packet = _packet()
    assert packet.replay_summary["semantic_match"] is None
    assert verify_execution_intent_formation_readiness_packet(packet) == packet


def test_invalid_eligibility_and_checked_at_are_refused() -> None:
    invalid = _eligibility().model_dump(mode="json")
    invalid["eligibility_hash"] = "0" * 64
    with pytest.raises(
        ExecutionIntentFormationReadinessError, match="EIFR_ELIGIBILITY_INVALID"
    ):
        build_execution_intent_formation_readiness_packet(invalid, NOW)
    with pytest.raises(
        ExecutionIntentFormationReadinessError, match="EIFR_CHECKED_AT_INVALID"
    ):
        build_execution_intent_formation_readiness_packet(
            _eligibility(), NOW.replace(tzinfo=None)
        )
    with pytest.raises(
        ExecutionIntentFormationReadinessError,
        match="EIFR_CHECKED_BEFORE_ELIGIBILITY_ISSUED",
    ):
        build_execution_intent_formation_readiness_packet(
            _eligibility(), NOW - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("source_decision_identity", "request_id", ""),
        ("source_decision_identity", "canonical_decision_id", ""),
        ("source_decision_identity", "canonical_decision_hash", ""),
        ("source_decision_identity", "canonical_decision_ts", "malformed"),
        ("candidate_identity", "actor_identity", ""),
        ("candidate_identity", "target_system", ""),
        ("candidate_identity", "target_resource", ""),
        ("candidate_identity", "action_contract_id", ""),
        ("evidence_lineage", "trustlog_artifact_ref", ""),
        ("evidence_lineage", "replay_artifact_ref", ""),
        ("evidence_lineage", "authority_evidence_ref", ""),
        ("evidence_lineage", "human_approval_receipt_ref", ""),
        ("evidence_lineage", "policy_snapshot_id", ""),
        ("evidence_lineage", "expected_state_fingerprint", ""),
    ],
)
def test_missing_or_malformed_source_fields_fail_closed(
    section: str, field: str, value: str
) -> None:
    raw = _eligibility().model_dump(mode="json")
    raw[section][field] = value
    with pytest.raises(
        ExecutionIntentFormationReadinessError, match="EIFR_ELIGIBILITY_INVALID"
    ):
        build_execution_intent_formation_readiness_packet(_resign_eligibility(raw), NOW)


def test_eligibility_verifier_runs_in_builder_and_verifier(monkeypatch) -> None:
    import veritas_os.policy.execution_intent_formation_readiness as module

    actual = module.verify_guarded_promotion_eligibility_packet
    calls = []

    def recording_verifier(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_guarded_promotion_eligibility_packet", recording_verifier
    )
    packet = module.build_execution_intent_formation_readiness_packet(
        _eligibility(), NOW
    )
    builder_calls = len(calls)
    module.verify_execution_intent_formation_readiness_packet(packet)
    assert builder_calls >= 2
    assert len(calls) == builder_calls + 1


@pytest.mark.parametrize(
    "path,value",
    [
        (("readiness_id",), "eifr:v1:sha256:" + "0" * 64),
        (("readiness_hash",), "0" * 64),
        (("checked_at",), "2031-01-01T00:00:00+00:00"),
        (("source_eligibility", "eligibility_hash"), "0" * 64),
        (("source_eligibility_hash",), "0" * 64),
        (("source_eligibility_packet", "eligibility_hash"), "0" * 64),
        (("source_handoff_hash",), "0" * 64),
        (("trusted_validation_context_hash",), "0" * 64),
        (("validation_result_hash",), "0" * 64),
        (("source_to_execution_intent_mapping", "decision_id"), "changed"),
        (("mapping_value_digest",), "0" * 64),
        (("required_field_presence", "decision_id"), "deferred"),
        (("source_decision_identity", "request_id"), "changed"),
        (("candidate_identity", "actor_identity"), "changed"),
        (("evidence_lineage", "trustlog_artifact_ref"), "changed"),
        (("replay_summary", "semantic_match"), False),
        (("replay_summary", "fields_changed"), ["changed"]),
        (("scope_limitations",), ["NOT_EXECUTION_INTENT"]),
    ],
)
def test_each_tamper_and_model_copy_bypass_is_refused(path, value) -> None:
    packet = _packet()
    raw = packet.model_dump(mode="json")
    target = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    bypass = packet.model_copy(update={path[0]: raw[path[0]]})
    with pytest.raises(ExecutionIntentFormationReadinessError):
        verify_execution_intent_formation_readiness_packet(bypass)


def test_semantic_tamper_is_refused_even_with_recomputed_packet_hash() -> None:
    raw = _packet().model_dump(mode="json")
    raw["source_to_execution_intent_mapping"]["decision_id"] = "changed"
    with pytest.raises(
        ExecutionIntentFormationReadinessError, match="EIFR_MAPPING_MISMATCH"
    ):
        verify_execution_intent_formation_readiness_packet(_resign(raw))


def test_construct_bypass_and_strict_json_refusals() -> None:
    packet = _packet()
    bypass = CanonicalExecutionIntentFormationReadinessPacket.model_construct(
        **(packet.model_dump(mode="python") | {"format_version": "bad"})
    )
    with pytest.raises(ExecutionIntentFormationReadinessError):
        verify_execution_intent_formation_readiness_packet(bypass)
    for value in (float("nan"), float("inf"), object(), {1: "bad"}, {"x"}):
        raw = packet.model_dump(mode="json")
        raw["source_eligibility"] = value
        with pytest.raises(ExecutionIntentFormationReadinessError):
            verify_execution_intent_formation_readiness_packet(raw)


def test_static_boundary_and_no_execution_artifact() -> None:
    source = Path(
        "veritas_os/policy/execution_intent_formation_readiness.py"
    ).read_text()
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden = {
        "ExecutionIntent",
        "BindReceipt",
        "hash_execution_intent",
        "build_execution_intent_trustlog_entry",
        "execute_bind_boundary",
        "execute_bind_adjudication",
        "WebhookBindAdapter",
        "ReferenceBindAdapter",
        "requests",
        "httpx",
        "subprocess",
    }
    assert imported.isdisjoint(forbidden)
    raw = _packet().model_dump(mode="json")
    assert "execution_intent_id" not in raw
    assert "bind_receipt_id" not in raw
    assert raw["required_field_presence"]["execution_intent_id"] == (
        "intentionally_deferred"
    )


def test_closed_schema_accepts_valid_and_rejects_nested_extra() -> None:
    schema = json.loads(
        Path("schemas/execution-intent-formation-readiness-v1.schema.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    raw = _packet().model_dump(mode="json")
    validator.validate(raw)
    raw["source_to_execution_intent_mapping"]["ignored"] = True
    assert list(validator.iter_errors(raw))
