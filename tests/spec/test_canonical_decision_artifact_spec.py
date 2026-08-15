"""Coherence tests for the specification-only canonical decision artifact."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.decision_semantics import (
    CANONICAL_GATE_DECISION_VALUES,
    FORBIDDEN_GATE_BUSINESS_COMBINATIONS,
)

SCHEMA_PATH = Path("schemas/canonical-decision-artifact-v1.schema.json")
SPEC_PATH = Path("docs/en/architecture/canonical-decision-artifact-v1.md")
HANDOFF_SPEC_PATH = Path(
    "docs/en/architecture/canonical-decision-to-bind-handoff-v1.md"
)
VECTOR_DIR = Path("docs/en/architecture/test-vectors/canonical-decision-artifact-v1")
FORMAT_VERSION = "canonical-decision-artifact/v1"
HASH_PROFILE = "veritas.canonical-decision/v1"
TOP_LEVEL_FIELDS = {
    "format_version",
    "hash_profile",
    "decision_id",
    "decision_hash",
    "decision_ts",
    "request_id",
    "source_contract",
    "decision",
}
DECISION_FIELDS = {
    "formation_status",
    "chosen_binding",
    "decision_status",
    "rejection_reason",
    "gate_decision",
    "business_decision",
    "next_action",
    "actionability_status",
    "requires_bind_before_execution",
    "human_review_required",
    "required_evidence",
    "missing_evidence",
    "satisfied_evidence",
    "rationale",
    "refusal_reason",
    "actionability_block_reason",
    "actionability_refusal_type",
    "governance_identity_binding",
    "lineage_promotability_binding",
    "transition_refusal_binding",
}
BIND_SOURCE_FIELDS = {
    "bind_outcome",
    "bind_failure_reason",
    "bind_reason_code",
    "bind_receipt_id",
    "execution_intent_id",
    "bound_execution_intent_id",
    "authority_check_result",
    "constraint_check_result",
    "drift_check_result",
    "risk_check_result",
    "bind_summary",
    "bind_operator_summary",
    "bind_operator_detail",
}
BINDING_SOURCES = {
    "chosen_binding": (
        "veritas.canonical-decision.chosen-value/v1",
        "chosen",
    ),
    "governance_identity_binding": (
        "veritas.canonical-decision.governance-identity/v1",
        "governance_identity",
    ),
    "lineage_promotability_binding": (
        "veritas.canonical-decision.lineage-promotability/v1",
        "lineage_promotability",
    ),
    "transition_refusal_binding": (
        "veritas.canonical-decision.transition-refusal/v1",
        "transition_refusal",
    ),
}


def _load_json(path: Path) -> dict[str, object]:
    """Load a repository-owned synthetic JSON vector."""
    return json.loads(path.read_text(encoding="utf-8"))


def _vectors() -> list[dict[str, object]]:
    """Return canonical decision vectors in deterministic filename order."""
    return [_load_json(path) for path in sorted(VECTOR_DIR.glob("vector-*.json"))]


def _reference_serialize_for_spec_fixture(value: object) -> str:
    """Serialize JSON for test-only verification of the normative profile."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reference_hash_for_spec_fixture(artifact: dict[str, object]) -> str:
    """Recompute a v1 decision hash only for specification fixtures."""
    preimage = {
        "profile": artifact["hash_profile"],
        "format_version": artifact["format_version"],
        "request_id": artifact["request_id"],
        "decision_ts": artifact["decision_ts"],
        "source_contract": artifact["source_contract"],
        "decision": artifact["decision"],
    }
    serialized = _reference_serialize_for_spec_fixture(preimage)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _reference_binding_digest_for_spec_fixture(
    profile: str,
    value: object,
) -> str:
    """Bind one normalized opaque source value in its documented domain."""
    serialized = _reference_serialize_for_spec_fixture(
        {"profile": profile, "value": value}
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _project_normalized_source_for_spec_fixture(
    normalized: dict[str, object],
) -> dict[str, object]:
    """Build the declared v1 projection for source-coherence tests only."""
    projected = {
        field: normalized[field]
        for field in (
            "decision_status",
            "rejection_reason",
            "gate_decision",
            "business_decision",
            "next_action",
            "actionability_status",
            "requires_bind_before_execution",
            "human_review_required",
            "required_evidence",
            "missing_evidence",
            "satisfied_evidence",
            "rationale",
            "refusal_reason",
            "actionability_block_reason",
            "actionability_refusal_type",
        )
    }
    projected["formation_status"] = (
        "COMPLETE" if normalized["governance_identity"] is not None else "INCOMPLETE"
    )
    for binding_field, (profile, source_field) in BINDING_SOURCES.items():
        value = normalized[source_field]
        projected[binding_field] = (
            {
                "profile": profile,
                "sha256": _reference_binding_digest_for_spec_fixture(
                    profile,
                    value,
                ),
            }
            if value is not None or source_field == "chosen"
            else None
        )
    return projected


def _post_bind_source_is_refused_for_spec_fixture(
    source: dict[str, object],
) -> bool:
    """Apply the documented test-only non-null post-Bind refusal rule."""
    return any(source.get(field) is not None for field in BIND_SOURCE_FIELDS)


def _normalize_aware_timestamp_for_spec_fixture(value: str) -> str:
    """Demonstrate the documented test-only aware-offset normalization."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("decision timestamp must be timezone-aware")
    utc_value = parsed.astimezone(timezone.utc)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def test_schema_and_all_expected_valid_vectors() -> None:
    """Check the schema and validate every expected valid artifact."""
    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )
    vectors = _vectors()

    assert len(vectors) == 15
    assert len({vector["vector_id"] for vector in vectors}) == 15
    assert all(vector["synthetic_fixture"] is True for vector in vectors)
    for vector in vectors:
        if vector["expected_schema_valid"] is True:
            validator.validate(vector["artifact"])
        elif vector["expected_schema_valid"] is False:
            with pytest.raises(ValidationError):
                validator.validate(vector["artifact"])


def test_schema_is_closed_versioned_and_has_exact_artifact_shape() -> None:
    """Pin the closed top-level and canonical projection field sets."""
    schema = _load_json(SCHEMA_PATH)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == TOP_LEVEL_FIELDS
    assert set(schema["properties"]) == TOP_LEVEL_FIELDS
    assert schema["properties"]["format_version"]["const"] == FORMAT_VERSION
    assert schema["properties"]["hash_profile"]["const"] == HASH_PROFILE
    decision = schema["$defs"]["decision"]
    assert decision["additionalProperties"] is False
    assert set(decision["required"]) == DECISION_FIELDS
    assert set(decision["properties"]) == DECISION_FIELDS


def test_hash_and_id_shapes_and_golden_bytes_are_stable() -> None:
    """Pin golden serialization, full digest, and content-addressed ID."""
    golden = _vectors()[0]
    artifact = golden["artifact"]
    serialized = _reference_serialize_for_spec_fixture(golden["canonical_preimage"])
    digest = _reference_hash_for_spec_fixture(artifact)

    assert serialized == golden["expected_canonical_serialized"]
    assert digest == golden["expected_decision_hash"]
    assert artifact["decision_hash"] == digest
    assert golden["expected_decision_id"] == f"cda:v1:sha256:{digest}"
    assert artifact["decision_id"] == golden["expected_decision_id"]
    assert len(digest) == 64
    assert artifact["request_id"] not in artifact["decision_id"]


def test_golden_source_round_trips_without_hidden_canonicalization() -> None:
    """Prove V01 is an actually normalized, producer-eligible source."""
    golden = _vectors()[0]
    source = golden["source_projection"]
    normalized = DecideResponse.model_validate(source).model_dump(mode="json")

    assert golden["expected_production"] == "EMIT"
    assert source["gate_decision"] == normalized["gate_decision"] == "hold"
    assert source["business_decision"] == normalized["business_decision"] == ("HOLD")
    assert source["human_review_required"] is False
    assert normalized["human_review_required"] is False
    assert (
        _project_normalized_source_for_spec_fixture(normalized)
        == golden["artifact"]["decision"]
    )


def test_emit_vectors_are_normalized_and_hash_only_vectors_are_explicit() -> None:
    """Separate producer eligibility from isolated hash sensitivity."""
    vectors = _vectors()

    assert {
        vector["vector_id"]
        for vector in vectors
        if vector["expected_production"] == "EMIT"
    } == {"CDA-V1-01", "CDA-V1-12"}
    assert all(
        vector["expected_production"] == "HASH_REFERENCE_ONLY"
        for vector in vectors[1:11]
    )
    for vector in vectors:
        if vector["expected_production"] != "EMIT":
            continue
        normalized = DecideResponse.model_validate(
            vector["source_projection"]
        ).model_dump(mode="json")
        assert (
            vector["source_projection"]["gate_decision"] == normalized["gate_decision"]
        )
        assert (
            _project_normalized_source_for_spec_fixture(normalized)
            == (vector["artifact"]["decision"])
        )


def test_golden_opaque_bindings_match_normalized_source_values() -> None:
    """Recompute each V01 field-specific digest from normalized source."""
    golden = _vectors()[0]
    normalized = DecideResponse.model_validate(golden["source_projection"]).model_dump(
        mode="json"
    )

    for binding_field, (profile, source_field) in BINDING_SOURCES.items():
        binding = golden["artifact"]["decision"][binding_field]
        assert binding["profile"] == profile
        assert binding["sha256"] == (
            _reference_binding_digest_for_spec_fixture(
                profile,
                normalized[source_field],
            )
        )


def test_every_included_mutation_changes_hash_and_id() -> None:
    """Prove the focused included-field sensitivity vectors."""
    vectors = _vectors()
    golden_hash = vectors[0]["expected_decision_hash"]
    golden_id = vectors[0]["expected_decision_id"]
    mutation_vectors = vectors[1:11]

    assert {vector["mutation"] for vector in mutation_vectors} == {
        "request_id",
        "decision_ts",
        "chosen binding",
        "gate_decision",
        "business_decision",
        "actionability_status",
        "human_review_required",
        "evidence state",
        "governance identity binding",
        "formation refusal/promotability state",
    }
    for vector in mutation_vectors:
        artifact = vector["artifact"]
        assert _reference_hash_for_spec_fixture(artifact) == artifact["decision_hash"]
        assert vector["expected_decision_hash"] != golden_hash
        assert vector["expected_decision_id"] != golden_id


def test_excluded_fields_and_bind_retroactivity_contract() -> None:
    """Pin exclusion stability and fail-closed post-Bind production."""
    vectors = {vector["vector_id"]: vector for vector in _vectors()}
    golden = vectors["CDA-V1-01"]
    excluded = vectors["CDA-V1-12"]
    post_bind = vectors["CDA-V1-13"]

    assert excluded["excluded_source_mutations"]
    assert excluded["expected_decision_hash"] == golden["expected_decision_hash"]
    assert excluded["expected_decision_id"] == golden["expected_decision_id"]
    assert post_bind["expected_production"] == "REFUSE"
    assert post_bind["expected_reason"] == "POST_BIND_SOURCE_REFUSED"
    assert "artifact" not in post_bind
    normalized = DecideResponse.model_validate(
        excluded["source_projection"]
    ).model_dump(mode="json")
    assert normalized["trust_log"] is not None
    assert normalized["user_summary"] == "Presentation only"
    assert {
        "meta",
        "persona",
        "alternatives",
        "options",
        "trust_log",
        "deterministic_replay",
        "user_summary",
    } <= set(excluded["excluded_source_mutations"])


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("bind_outcome", "BLOCKED"),
        ("bind_failure_reason", "synthetic"),
        ("bind_reason_code", "SYNTHETIC"),
        ("bind_receipt_id", "bind-synthetic"),
        ("execution_intent_id", "intent-synthetic"),
        ("bound_execution_intent_id", "intent-synthetic"),
        ("authority_check_result", {"status": "synthetic"}),
        ("constraint_check_result", {"status": "synthetic"}),
        ("drift_check_result", {"status": "synthetic"}),
        ("risk_check_result", {"status": "synthetic"}),
        ("bind_summary", {"bind_outcome": "ROLLED_BACK"}),
        ("bind_operator_summary", {"bind_outcome": "BLOCKED"}),
        ("bind_operator_detail", {"bind_outcome": "ROLLED_BACK"}),
    ),
)
def test_every_current_post_bind_source_field_is_refused(
    field: str,
    value: object,
) -> None:
    """Refuse every current non-null Bind result or operator surface."""
    source = deepcopy(_vectors()[0]["source_projection"])
    source[field] = value
    normalized = DecideResponse.model_validate(source).model_dump(mode="json")

    assert set(_vectors()[12]["post_bind_source_fields"]) == BIND_SOURCE_FIELDS
    assert normalized[field] is not None
    assert _post_bind_source_is_refused_for_spec_fixture(normalized)


def test_null_post_bind_fields_are_not_populated() -> None:
    """Define populated as non-null, while retaining fail-closed values."""
    source = {field: None for field in BIND_SOURCE_FIELDS}

    assert BIND_SOURCE_FIELDS <= set(DecideResponse.model_fields)
    assert not _post_bind_source_is_refused_for_spec_fixture(source)


def test_timestamp_contract_and_deterministic_normalization() -> None:
    """Require exact UTC microseconds and reject naive/invalid timestamps."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}

    assert (
        _normalize_aware_timestamp_for_spec_fixture("2031-02-03T05:05:06.123456+01:00")
        == "2031-02-03T04:05:06.123456Z"
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        _normalize_aware_timestamp_for_spec_fixture("2031-02-03T04:05:06.123456")
    assert by_id["CDA-V1-14"]["expected_reason"] == "NAIVE_TIMESTAMP"
    assert by_id["CDA-V1-15"]["expected_reason"] == "INVALID_TIMESTAMP"


def test_hash_preimage_has_no_self_reference_or_response_shortcut() -> None:
    """Prove exact preimage keys and the non-circular construction."""
    golden = _vectors()[0]
    preimage = golden["canonical_preimage"]

    assert set(preimage) == {
        "profile",
        "format_version",
        "request_id",
        "decision_ts",
        "source_contract",
        "decision",
    }
    assert "decision_hash" not in preimage
    assert "decision_id" not in preimage
    specification = SPEC_PATH.read_text(encoding="utf-8")
    assert "`SHA256(response.json())` is prohibited" in specification
    assert "MUST NOT be inferred or backfilled" in specification


def test_schema_cannot_carry_execution_bind_or_self_declared_validity() -> None:
    """Keep execution, Bind, and trust declarations outside the artifact."""
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    forbidden = {
        '"execution_intent"',
        '"bind_receipt"',
        '"execution_authorized"',
        '"adapter"',
        '"external_effect"',
        '"verified"',
    }

    assert not forbidden.intersection(schema_text.splitlines())
    assert all(term not in schema_text for term in forbidden)


def test_closed_vocabularies_match_normalized_source_contract() -> None:
    """Pin canonical vocabularies and exclude every legacy gate alias."""
    schema = _load_json(SCHEMA_PATH)
    decision = schema["$defs"]["decision"]["properties"]

    assert set(decision["decision_status"]["enum"]) == {
        "allow",
        "modify",
        "rejected",
        "block",
        "abstain",
    }
    assert set(decision["gate_decision"]["enum"]) == set(CANONICAL_GATE_DECISION_VALUES)
    assert not {"allow", "deny", "modify", "rejected", "abstain"} & set(
        decision["gate_decision"]["enum"]
    )
    assert "unknown" not in decision["gate_decision"]["enum"]
    assert set(decision["business_decision"]["enum"]) == {
        "APPROVE",
        "DENY",
        "HOLD",
        "REVIEW_REQUIRED",
        "POLICY_DEFINITION_REQUIRED",
        "EVIDENCE_REQUIRED",
    }
    assert set(decision["actionability_status"]["enum"]) == {
        "reviewable_only",
        "bind_required_before_execution",
        "blocked",
        "human_review_required",
        "formation_transition_refused",
    }


@pytest.mark.parametrize(
    ("status", "requires_bind", "review_required"),
    (
        ("reviewable_only", False, False),
        ("bind_required_before_execution", False, False),
        ("human_review_required", False, True),
        ("blocked", True, False),
        ("formation_transition_refused", True, True),
        ("human_review_required", True, False),
    ),
)
def test_actionability_boundary_contradictions_are_schema_invalid(
    status: str,
    requires_bind: bool,
    review_required: bool,
) -> None:
    """Reject contradictory pre-Bind actionability boundary combinations."""
    artifact = deepcopy(_vectors()[0]["artifact"])
    artifact["decision"].update(
        actionability_status=status,
        requires_bind_before_execution=requires_bind,
        human_review_required=review_required,
    )

    with pytest.raises(ValidationError):
        Draft202012Validator(_load_json(SCHEMA_PATH)).validate(artifact)


def test_actionable_after_bind_is_post_bind_only_and_schema_invalid() -> None:
    """Tie the excluded status to runtime's committed bound-lineage rule."""
    artifact = deepcopy(_vectors()[0]["artifact"])
    artifact["decision"]["actionability_status"] = "actionable_after_bind"
    pipeline_contract = Path("veritas_os/core/pipeline/pipeline_response.py").read_text(
        encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        Draft202012Validator(_load_json(SCHEMA_PATH)).validate(artifact)
    for bound_lineage_requirement in (
        'normalized_outcome == "COMMITTED"',
        "normalized_bind_receipt_id is not None",
        "normalized_execution_intent_id is not None",
        'status = "actionable_after_bind"',
    ):
        assert bound_lineage_requirement in pipeline_contract


def test_golden_actionability_boundary_remains_valid() -> None:
    """Preserve V01's coherent pre-Bind reviewable-only boundary."""
    golden = _vectors()[0]["artifact"]

    assert golden["decision"]["actionability_status"] == "reviewable_only"
    assert golden["decision"]["requires_bind_before_execution"] is True
    Draft202012Validator(_load_json(SCHEMA_PATH)).validate(golden)


def test_schema_mirrors_gate_business_human_review_invariants() -> None:
    """Reject the same coupled semantic combinations as DecideResponse."""
    schema = _load_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    artifact = deepcopy(_vectors()[0]["artifact"])
    invalid_tuples = [
        ("proceed", "HOLD", True),
        ("hold", "APPROVE", False),
        ("block", "APPROVE", False),
        ("proceed", "DENY", False),
        ("hold", "REVIEW_REQUIRED", True),
        ("human_review_required", "HOLD", True),
        ("human_review_required", "REVIEW_REQUIRED", False),
    ]

    assert FORBIDDEN_GATE_BUSINESS_COMBINATIONS == frozenset(
        {
            ("block", "APPROVE"),
            ("hold", "APPROVE"),
            ("proceed", "DENY"),
        }
    )
    for gate, business, review_required in invalid_tuples:
        candidate = deepcopy(artifact)
        candidate["decision"].update(
            gate_decision=gate,
            business_decision=business,
            human_review_required=review_required,
        )
        with pytest.raises(ValidationError):
            validator.validate(candidate)
        with pytest.raises(ValueError):
            DecideResponse.model_validate(
                {
                    "gate_decision": gate,
                    "business_decision": business,
                    "human_review_required": review_required,
                }
            )


@pytest.mark.parametrize(
    ("binding_field", "wrong_profile"),
    (
        ("chosen_binding", "unknown-profile/v1"),
        (
            "governance_identity_binding",
            "veritas.canonical-decision.chosen-value/v1",
        ),
        (
            "transition_refusal_binding",
            "veritas.canonical-decision.governance-identity/v1",
        ),
    ),
)
def test_wrong_or_swapped_binding_profiles_are_schema_invalid(
    binding_field: str,
    wrong_profile: str,
) -> None:
    """Prevent opaque binding digest domain substitution."""
    artifact = deepcopy(_vectors()[0]["artifact"])
    artifact["decision"][binding_field]["profile"] = wrong_profile

    with pytest.raises(ValidationError):
        Draft202012Validator(_load_json(SCHEMA_PATH)).validate(artifact)


@pytest.mark.parametrize(
    ("formation_status", "binding"),
    (("COMPLETE", None), ("INCOMPLETE", "golden")),
)
def test_formation_status_and_governance_binding_cannot_contradict(
    formation_status: str,
    binding: str | None,
) -> None:
    """Pin formation completeness to governance binding presence only."""
    artifact = deepcopy(_vectors()[0]["artifact"])
    artifact["decision"]["formation_status"] = formation_status
    if binding is None:
        artifact["decision"]["governance_identity_binding"] = None

    with pytest.raises(ValidationError):
        Draft202012Validator(_load_json(SCHEMA_PATH)).validate(artifact)


def test_non_authority_non_execution_and_incomplete_governance_are_explicit() -> None:
    """Pin semantic non-claims and absent-governance formation behavior."""
    specification = SPEC_PATH.read_text(encoding="utf-8")

    for invariant in (
        "`ALLOW != authority`",
        "`APPROVE != Human Approval Receipt`",
        "`chosen != canonical executable action`",
        "`next_action != intended_action`",
        "`READY_FOR_GUARDED_PROMOTION != execution`",
        "`INCOMPLETE` means it is unavailable",
    ):
        assert invariant in specification


def test_mismatched_id_is_not_accepted_and_request_id_is_insufficient() -> None:
    """Prove ID verification requires the full recomputed decision digest."""
    artifact = deepcopy(_vectors()[0]["artifact"])
    expected_id = f"cda:v1:sha256:{_reference_hash_for_spec_fixture(artifact)}"
    artifact["decision_id"] = "cda:v1:sha256:" + ("0" * 64)

    assert artifact["decision_id"] != expected_id
    assert artifact["request_id"] != expected_id


def test_handoff_mapping_names_all_four_verified_artifact_values() -> None:
    """Keep future artifact-to-handoff mapping explicit and non-operative."""
    handoff = HANDOFF_SPEC_PATH.read_text(encoding="utf-8")

    for mapping in (
        "`artifact.request_id` to `source_decision.request_id`",
        "`artifact.decision_id` to `source_decision.canonical_decision_id`",
        "`artifact.decision_hash` to `source_decision.canonical_decision_hash`",
        "`artifact.decision_ts` to `source_decision.canonical_decision_ts`",
    ):
        assert mapping in handoff
    assert "Merely\ncopying these four strings is insufficient for READY" in handoff
