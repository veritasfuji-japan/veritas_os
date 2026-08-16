"""Security and integrity tests for guarded-promotion eligibility packets."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.guarded_promotion_eligibility import (
    TRUSTED_CONTEXT_DOMAIN,
    GuardedPromotionEligibilityError,
    _digest,
    _packet_hash,
    build_guarded_promotion_eligibility_packet,
    verify_guarded_promotion_eligibility_packet,
)
from veritas_os.tests.test_canonical_decision_handoff import _complete_context

VECTOR = Path(
    "docs/en/architecture/test-vectors/decision-to-bind-handoff-v1/vector-01.json"
)
NOW = datetime(2030, 1, 1, 0, 0, 2, tzinfo=timezone.utc)


def _ready():
    handoff = json.loads(VECTOR.read_text())["input"]
    return handoff, _complete_context(handoff)


def _packet():
    handoff, context = _ready()
    return build_guarded_promotion_eligibility_packet(handoff, context, NOW, NOW)


def _resign(raw: dict, *, context_changed: bool = False) -> dict:
    """Recompute test-only digests so a mutation reaches semantic checks."""
    if context_changed:
        raw["trusted_validation_context_hash"] = _digest(
            TRUSTED_CONTEXT_DOMAIN, raw["trusted_validation_context"]
        )
    raw["eligibility_hash"] = _packet_hash(raw)
    raw["eligibility_id"] = f"gpe:v1:sha256:{raw['eligibility_hash']}"
    return raw


def test_ready_packet_is_deterministic_verified_and_has_no_authority() -> None:
    packet = _packet()
    assert verify_guarded_promotion_eligibility_packet(packet) == packet
    assert packet.validation_status == "READY_FOR_GUARDED_PROMOTION"
    assert packet.ready_for_guarded_promotion is True
    assert packet.fail_closed is False
    expected_source = dict(packet.source_handoff["source_decision"])
    expected_source.pop("gate_decision")
    assert packet.source_decision_identity == expected_source
    assert "NOT_EXECUTION_INTENT" in packet.scope_limitations
    assert "NOT_BIND_RECEIPT" in packet.scope_limitations
    assert _packet() == packet


@pytest.mark.parametrize(
    "mutation",
    [
        lambda h: h.__setitem__("authority_evidence", None),
        lambda h: h.__setitem__("human_approval_evidence", None),
        lambda h: h["trustlog_lineage"].__setitem__("verified", False),
        lambda h: h["replay_lineage"].__setitem__("verified", False),
        lambda h: h["target_context"].__setitem__("target_system", "other"),
        lambda h: h.__setitem__("candidate_hash", "changed"),
        lambda h: h["policy_lineage"].__setitem__("superseded", True),
        lambda h: h["expected_state"].__setitem__(
            "observed_at", "2020-01-01T00:00:00Z"
        ),
        lambda h: h.__setitem__("expires_at", "2029-01-01T00:00:00Z"),
        lambda h: h["source_decision"].__setitem__(
            "canonical_decision_ts", "2031-01-01T00:00:00Z"
        ),
    ],
)
def test_non_ready_handoff_is_refused(mutation) -> None:
    handoff, _ = _ready()
    mutation(handoff)
    context = _complete_context(handoff)
    with pytest.raises(GuardedPromotionEligibilityError, match="GPE_HANDOFF_NOT_READY"):
        build_guarded_promotion_eligibility_packet(handoff, context, NOW, NOW)


@pytest.mark.parametrize("which", ["evaluated", "issued"])
def test_naive_times_are_refused(which: str) -> None:
    handoff, context = _ready()
    naive = NOW.replace(tzinfo=None)
    with pytest.raises(GuardedPromotionEligibilityError, match="INVALID"):
        build_guarded_promotion_eligibility_packet(
            handoff, context, naive if which == "evaluated" else NOW,
            naive if which == "issued" else NOW,
        )


def test_packet_timeline_accepts_equal_and_later_issue_times() -> None:
    handoff, context = _ready()
    equal = build_guarded_promotion_eligibility_packet(
        handoff, context, NOW, NOW
    )
    later = build_guarded_promotion_eligibility_packet(
        handoff, context, NOW, NOW + timedelta(seconds=1)
    )
    assert verify_guarded_promotion_eligibility_packet(equal) == equal
    assert verify_guarded_promotion_eligibility_packet(later) == later


def test_packet_timeline_rejects_issue_before_evaluation() -> None:
    handoff, context = _ready()
    with pytest.raises(
        GuardedPromotionEligibilityError,
        match="GPE_ISSUED_BEFORE_EVALUATED",
    ):
        build_guarded_promotion_eligibility_packet(
            handoff, context, NOW, NOW - timedelta(seconds=1)
        )
    raw = _packet().model_dump(mode="json")
    raw["issued_at"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(
        GuardedPromotionEligibilityError,
        match="GPE_ISSUED_BEFORE_EVALUATED",
    ):
        verify_guarded_promotion_eligibility_packet(_resign(raw))


def test_semantic_divergence_is_preserved_and_is_not_a_gate() -> None:
    handoff, _ = _ready()
    handoff["replay_lineage"].update(
        semantic_match=False,
        fields_changed=["outcome.status"],
    )
    replay_record = next(
        item
        for item in handoff["provenance"]
        if item["field_path"] == "replay_lineage"
    )
    replay_record["value"] = deepcopy(handoff["replay_lineage"])
    packet = build_guarded_promotion_eligibility_packet(
        handoff, _complete_context(handoff), NOW, NOW
    )
    assert packet.replay_summary["semantic_match"] is False
    assert packet.replay_summary["fields_changed"] == ["outcome.status"]
    assert verify_guarded_promotion_eligibility_packet(packet) == packet


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.__setitem__("ignored", "must-not-be-ignored"),
        lambda c: c["value_assertions"][0].__setitem__("ignored", True),
        lambda c: c["candidate_hash_binding"].__setitem__("ignored", True),
        lambda c: c["authority_requirement_binding"].__setitem__(
            "ignored", True
        ),
        lambda c: c.__setitem__("candidate_hash_binding", {}),
        lambda c: c.__setitem__("authority_requirement_binding", {}),
        lambda c: c["value_assertions"][0].__setitem__(
            "verified_at", "malformed"
        ),
        lambda c: c["value_assertions"][0].pop("field_path"),
    ],
)
def test_malformed_or_unused_trusted_context_is_rejected(mutation) -> None:
    raw = _packet().model_dump(mode="json")
    mutation(raw["trusted_validation_context"])
    with pytest.raises(
        GuardedPromotionEligibilityError,
        match="GPE_CONTEXT_RECONSTRUCTION_FAILED",
    ):
        verify_guarded_promotion_eligibility_packet(
            _resign(raw, context_changed=True)
        )


@pytest.mark.parametrize(
    "path,value",
    [
        (("eligibility_id",), "gpe:v1:sha256:" + "0" * 64),
        (("eligibility_hash",), "0" * 64),
        (("source_handoff_hash",), "0" * 64),
        (("trusted_validation_context_hash",), "0" * 64),
        (("validation_result_hash",), "0" * 64),
        (("validation_result", "structure_valid"), False),
        (("source_decision_identity", "request_id"), "substituted"),
        (("candidate_identity", "candidate_id"), "substituted"),
        (("evidence_lineage", "trustlog_artifact_ref"), "substituted"),
        (("replay_summary", "semantic_match"), False),
        (("scope_limitations",), ["NOT_EXECUTION_INTENT"]),
    ],
)
def test_tamper_and_instance_bypass_are_refused(path, value) -> None:
    packet = _packet()
    raw = packet.model_dump(mode="json")
    target = raw
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    bypass = packet.model_copy(update={path[0]: raw[path[0]]})
    with pytest.raises(GuardedPromotionEligibilityError):
        verify_guarded_promotion_eligibility_packet(bypass)


def test_construct_bypass_and_unsupported_json_are_refused() -> None:
    packet = _packet()
    bypass = type(packet).model_construct(
        **(packet.model_dump(mode="python") | {"format_version": "bad"})
    )
    with pytest.raises(GuardedPromotionEligibilityError):
        verify_guarded_promotion_eligibility_packet(bypass)
    handoff, context = _ready()
    handoff["bad"] = object()
    with pytest.raises(GuardedPromotionEligibilityError):
        build_guarded_promotion_eligibility_packet(handoff, context, NOW, NOW)


def test_static_import_boundary() -> None:
    source = Path("veritas_os/policy/guarded_promotion_eligibility.py").read_text()
    imported = {alias.name for node in ast.walk(ast.parse(source))
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names}
    forbidden = {"ExecutionIntent", "BindReceipt", "execute_bind_boundary",
                 "execute_bind_adjudication", "WebhookBindAdapter",
                 "ReferenceBindAdapter", "requests", "httpx", "subprocess"}
    assert imported.isdisjoint(forbidden)


def test_closed_schema_accepts_packet_and_rejects_nested_extra_fields() -> None:
    schema = json.loads(
        Path(
            "schemas/guarded-promotion-eligibility-packet-v1.schema.json"
        ).read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    raw = _packet().model_dump(mode="json")
    validator.validate(raw)
    raw["trusted_validation_context"]["ignored"] = True
    assert list(validator.iter_errors(raw))
