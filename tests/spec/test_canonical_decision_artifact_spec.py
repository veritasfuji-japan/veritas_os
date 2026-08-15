"""Coherence tests for the specification-only canonical decision artifact."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA_PATH = Path("schemas/canonical-decision-artifact-v1.schema.json")
SPEC_PATH = Path(
    "docs/en/architecture/canonical-decision-artifact-v1.md"
)
HANDOFF_SPEC_PATH = Path(
    "docs/en/architecture/canonical-decision-to-bind-handoff-v1.md"
)
VECTOR_DIR = Path(
    "docs/en/architecture/test-vectors/canonical-decision-artifact-v1"
)
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


def _load_json(path: Path) -> dict[str, object]:
    """Load a repository-owned synthetic JSON vector."""
    return json.loads(path.read_text(encoding="utf-8"))


def _vectors() -> list[dict[str, object]]:
    """Return canonical decision vectors in deterministic filename order."""
    return [
        _load_json(path)
        for path in sorted(VECTOR_DIR.glob("vector-*.json"))
    ]


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
    serialized = _reference_serialize_for_spec_fixture(
        golden["canonical_preimage"]
    )
    digest = _reference_hash_for_spec_fixture(artifact)

    assert serialized == golden["expected_canonical_serialized"]
    assert digest == golden["expected_decision_hash"]
    assert artifact["decision_hash"] == digest
    assert golden["expected_decision_id"] == f"cda:v1:sha256:{digest}"
    assert artifact["decision_id"] == golden["expected_decision_id"]
    assert len(digest) == 64
    assert artifact["request_id"] not in artifact["decision_id"]


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
        assert _reference_hash_for_spec_fixture(artifact) == artifact[
            "decision_hash"
        ]
        assert vector["expected_decision_hash"] != golden_hash
        assert vector["expected_decision_id"] != golden_id


def test_excluded_fields_and_bind_retroactivity_contract() -> None:
    """Pin exclusion stability and fail-closed post-Bind production."""
    vectors = {vector["vector_id"]: vector for vector in _vectors()}
    golden = vectors["CDA-V1-01"]
    excluded = vectors["CDA-V1-12"]
    post_bind = vectors["CDA-V1-13"]

    assert excluded["excluded_source_mutations"]
    assert excluded["expected_decision_hash"] == golden[
        "expected_decision_hash"
    ]
    assert excluded["expected_decision_id"] == golden["expected_decision_id"]
    assert post_bind["expected_production"] == "REFUSE"
    assert post_bind["expected_reason"] == "POST_BIND_SOURCE_REFUSED"
    assert "artifact" not in post_bind


def test_timestamp_contract_and_deterministic_normalization() -> None:
    """Require exact UTC microseconds and reject naive/invalid timestamps."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}

    assert _normalize_aware_timestamp_for_spec_fixture(
        "2031-02-03T05:05:06.123456+01:00"
    ) == "2031-02-03T04:05:06.123456Z"
    with pytest.raises(ValueError, match="timezone-aware"):
        _normalize_aware_timestamp_for_spec_fixture(
            "2031-02-03T04:05:06.123456"
        )
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


def test_non_authority_non_execution_and_incomplete_governance_are_explicit() -> None:
    """Pin semantic non-claims and absent-governance formation behavior."""
    specification = SPEC_PATH.read_text(encoding="utf-8")

    for invariant in (
        "`ALLOW != authority`",
        "`APPROVE != Human Approval Receipt`",
        "`chosen != canonical executable action`",
        "`next_action != intended_action`",
        "`READY_FOR_GUARDED_PROMOTION != execution`",
        "`formation_status=INCOMPLETE`",
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
