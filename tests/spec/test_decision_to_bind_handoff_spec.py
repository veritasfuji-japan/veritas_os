"""Coherence tests for the specification-only Decision-to-Bind contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SCHEMA_PATH = Path("schemas/decision-to-bind-handoff-v1.schema.json")
VECTOR_DIR = Path(
    "docs/en/architecture/test-vectors/decision-to-bind-handoff-v1"
)
ALLOWED_STATUSES = {
    "INCOMPLETE",
    "REVIEW_REQUIRED",
    "INVALID",
    "STRUCTURALLY_REFUSED",
    "READY_FOR_GUARDED_PROMOTION",
}
READY_PROVENANCE_PATHS = {
    "source_decision.request_id",
    "source_decision.canonical_decision_id",
    "source_decision.canonical_decision_hash",
    "source_decision.canonical_decision_ts",
    "candidate.actor_identity",
    "candidate.target_system",
    "candidate.target_resource",
    "candidate.canonical_action",
    "candidate_hash",
    "trustlog_lineage",
    "replay_lineage",
    "policy_lineage",
    "authority_requirement",
    "authority_evidence",
    "human_approval_requirement",
    "human_approval_evidence",
    "expected_state",
}
DISALLOWED_READY_PROVENANCE_CLASSES = {
    "UNAVAILABLE",
    "UNVERIFIED_STRUCTURED_INPUT",
}


def _load_json(path: Path) -> dict[str, object]:
    """Load one repository-owned JSON specification artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _vectors() -> list[dict[str, object]]:
    """Return deterministic vectors in their filename order."""
    return [_load_json(path) for path in sorted(VECTOR_DIR.glob("vector-*.json"))]


def _assert_ready_provenance(handoff: dict[str, object]) -> None:
    """Assert the documented READY fixture provenance contract.

    This test-only coherence assertion is deliberately not the production
    handoff validator; runtime behavior is tested in its dedicated test module.
    """
    provenance = handoff["provenance"]
    by_path = {record["field_path"]: record for record in provenance}

    assert READY_PROVENANCE_PATHS <= set(by_path)
    for field_path in READY_PROVENANCE_PATHS:
        record = by_path[field_path]
        assert record["verification_status"] == "VERIFIED"
        assert (
            record["provenance_class"]
            not in DISALLOWED_READY_PROVENANCE_CLASSES
        )


def test_schema_and_all_26_vector_inputs_are_valid() -> None:
    """Validate the schema itself and every synthetic handoff input."""
    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    vectors = _vectors()

    assert len(vectors) == 26
    for vector in vectors:
        validator.validate(vector["input"])


def test_vector_metadata_is_unique_safe_and_specification_only() -> None:
    """Ensure fixture metadata cannot imply execution or an external effect."""
    vectors = _vectors()
    vector_ids = [vector["vector_id"] for vector in vectors]

    assert len(vector_ids) == len(set(vector_ids))
    for vector in vectors:
        expected_status = vector["expected_handoff_status"]
        assert expected_status in ALLOWED_STATUSES
        assert vector["input"]["handoff_status"] == expected_status
        assert vector["input"]["refusal_reason_codes"] == vector[
            "expected_reason_codes"
        ]
        assert vector["execution_intent_created"] is False
        assert vector["bind_invoked"] is False
        assert vector["external_effect"] is False
        assert vector["synthetic_fixture"] is True
        if expected_status != "READY_FOR_GUARDED_PROMOTION":
            assert vector["expected_reason_codes"]


def test_every_provenance_record_has_value_and_unique_field_path() -> None:
    """Require explicit values and unambiguous coverage in every fixture."""
    for vector in _vectors():
        provenance = vector["input"]["provenance"]
        field_paths = [record["field_path"] for record in provenance]

        assert len(field_paths) == len(set(field_paths))
        assert all("value" in record for record in provenance)


def test_ready_fixture_has_complete_verified_provenance() -> None:
    """Pin complete, verified provenance for the sole synthetic READY case."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}
    ready_handoff = by_id["DTBH-V1-01"]["input"]

    assert len(ready_handoff["provenance"]) == len(READY_PROVENANCE_PATHS)
    _assert_ready_provenance(ready_handoff)


def test_removing_any_ready_path_fails_the_coherence_assertion() -> None:
    """Prove that no mandatory READY provenance path is optional."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}
    ready_handoff = by_id["DTBH-V1-01"]["input"]

    for removed_path in READY_PROVENANCE_PATHS:
        incomplete = deepcopy(ready_handoff)
        incomplete["provenance"] = [
            record
            for record in incomplete["provenance"]
            if record["field_path"] != removed_path
        ]
        with pytest.raises(AssertionError):
            _assert_ready_provenance(incomplete)


def test_only_ready_vector_satisfies_ready_provenance_contract() -> None:
    """Prevent non-READY fixtures from accidentally representing readiness."""
    for vector in _vectors():
        paths = {
            record["field_path"]
            for record in vector["input"]["provenance"]
        }
        if vector["expected_handoff_status"] == "READY_FOR_GUARDED_PROMOTION":
            assert READY_PROVENANCE_PATHS <= paths
        else:
            assert not READY_PROVENANCE_PATHS <= paths


def test_positive_and_structural_refusal_semantics_are_explicit() -> None:
    """Protect READY meaning and the non-promotable lineage invariant."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}

    assert (
        by_id["DTBH-V1-01"]["expected_handoff_status"]
        == "READY_FOR_GUARDED_PROMOTION"
    )
    assert by_id["DTBH-V1-01"]["expected_reason_codes"] == []
    for vector_id in ("DTBH-V1-19", "DTBH-V1-20"):
        assert by_id[vector_id]["expected_handoff_status"] == "STRUCTURALLY_REFUSED"
        assert "HANDOFF_LINEAGE_NON_PROMOTABLE" in by_id[vector_id][
            "expected_reason_codes"
        ]
    assert by_id["DTBH-V1-20"]["input"]["authority_evidence"] is not None


def test_forbidden_inference_and_binding_vectors_fail_closed() -> None:
    """Pin representative semantic-laundering and substitution refusals."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}

    for vector_id in ("DTBH-V1-09", "DTBH-V1-10", "DTBH-V1-13"):
        assert by_id[vector_id]["expected_handoff_status"] == "INVALID"
    for vector_id in ("DTBH-V1-21", "DTBH-V1-23"):
        assert by_id[vector_id]["expected_handoff_status"] == "INCOMPLETE"
        assert by_id[vector_id]["expected_reason_codes"] == [
            "HANDOFF_AUTHORITY_EVIDENCE_MISSING"
        ]
        assert by_id[vector_id]["forbidden_inference"]


def test_missing_authority_vectors_have_equivalent_runtime_inputs() -> None:
    """Prove untrusted declarations cannot distinguish vectors 08 and 21."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}
    ignored_fields = {
        "handoff_id",
        "handoff_status",
        "refusal_reason_codes",
    }

    def substantive_input(vector_id: str) -> dict[str, object]:
        handoff = by_id[vector_id]["input"]
        return {
            key: value
            for key, value in handoff.items()
            if key not in ignored_fields
        }

    vector_08 = by_id["DTBH-V1-08"]
    vector_21 = by_id["DTBH-V1-21"]
    assert substantive_input("DTBH-V1-08") == substantive_input("DTBH-V1-21")
    assert vector_08["expected_handoff_status"] == "INCOMPLETE"
    assert vector_21["expected_handoff_status"] == "INCOMPLETE"
    assert vector_08["expected_reason_codes"] == vector_21[
        "expected_reason_codes"
    ] == ["HANDOFF_AUTHORITY_EVIDENCE_MISSING"]


def test_non_authoritative_signals_do_not_satisfy_required_evidence() -> None:
    """Pin missing-evidence outcomes independently of tempting source signals."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}
    identity_vector = by_id["DTBH-V1-23"]
    approval_vector = by_id["DTBH-V1-22"]

    assert identity_vector["input"]["source_decision"][
        "authenticated_api_user"
    ]
    assert identity_vector["input"]["authority_evidence"] is None
    assert identity_vector["expected_handoff_status"] == "INCOMPLETE"
    assert identity_vector["expected_reason_codes"] == [
        "HANDOFF_AUTHORITY_EVIDENCE_MISSING"
    ]

    assert approval_vector["input"]["source_decision"][
        "business_decision"
    ] == "APPROVE"
    assert approval_vector["input"]["human_approval_evidence"] is None
    assert approval_vector["expected_handoff_status"] == "REVIEW_REQUIRED"
    assert approval_vector["expected_reason_codes"] == [
        "HANDOFF_APPROVAL_EVIDENCE_MISSING"
    ]


def test_schema_statuses_and_reason_codes_cover_vectors() -> None:
    """Keep documented vector expectations inside the machine contract."""
    schema = _load_json(SCHEMA_PATH)
    schema_statuses = set(schema["properties"]["handoff_status"]["enum"])
    schema_reasons = set(
        schema["properties"]["refusal_reason_codes"]["items"]["enum"]
    )

    assert schema_statuses == ALLOWED_STATUSES
    for vector in _vectors():
        assert set(vector["expected_reason_codes"]) <= schema_reasons


def test_candidate_mutation_and_target_context_substitution_are_distinct() -> None:
    """Pin V05's two failures separately from V24 context substitution."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}
    vector_01 = by_id["DTBH-V1-01"]
    vector_05 = by_id["DTBH-V1-05"]
    vector_24 = by_id["DTBH-V1-24"]

    assert vector_05["expected_handoff_status"] == "INVALID"
    assert vector_05["expected_reason_codes"] == [
        "HANDOFF_TARGET_CONTEXT_MISMATCH",
        "HANDOFF_CANDIDATE_HASH_MISMATCH",
    ]
    assert vector_05["input"]["candidate"] != vector_01["input"]["candidate"]
    assert vector_05["input"]["candidate"]["target_resource"] == (
        "account:fixture:B"
    )
    assert vector_05["input"]["target_context"]["target_resource"] == (
        "account:fixture:A"
    )
    assert vector_05["input"]["authority_evidence"]["target_scope"] == (
        vector_05["input"]["candidate"]["target_resource"]
    )
    assert vector_05["input"]["human_approval_evidence"][
        "target_resource"
    ] == vector_05["input"]["candidate"]["target_resource"]
    assert (
        vector_05["input"]["candidate"]["target_resource"]
        != vector_01["input"]["candidate"]["target_resource"]
    )

    assert vector_24["expected_handoff_status"] == "INVALID"
    assert vector_24["expected_reason_codes"] == [
        "HANDOFF_TARGET_CONTEXT_MISMATCH"
    ]
    assert (
        vector_24["input"]["candidate"]["target_system"],
        vector_24["input"]["candidate"]["target_resource"],
    ) != (
        vector_24["input"]["target_context"]["target_system"],
        vector_24["input"]["target_context"]["target_resource"],
    )
    assert "HANDOFF_CANDIDATE_HASH_MISMATCH" not in vector_24[
        "expected_reason_codes"
    ]


def test_target_context_mismatch_has_a_distinct_canonical_reason_code() -> None:
    """Keep the cross-field target reason in schema and specification."""
    schema = _load_json(SCHEMA_PATH)
    schema_reasons = set(
        schema["properties"]["refusal_reason_codes"]["items"]["enum"]
    )
    specification = Path(
        "docs/en/architecture/canonical-decision-to-bind-handoff-v1.md"
    ).read_text(encoding="utf-8")

    candidate_reason = "HANDOFF_CANDIDATE_HASH_MISMATCH"
    target_context_reason = "HANDOFF_TARGET_CONTEXT_MISMATCH"
    assert candidate_reason != target_context_reason
    assert target_context_reason in schema_reasons
    assert target_context_reason in specification


def test_future_canonical_decision_artifact_mapping_is_non_operational() -> None:
    """Pin the future verified artifact source without changing readiness."""
    specification = Path(
        "docs/en/architecture/canonical-decision-to-bind-handoff-v1.md"
    ).read_text(encoding="utf-8")

    assert "CanonicalDecisionArtifact v1" in specification
    for field_name in (
        "canonical_decision_id",
        "canonical_decision_hash",
        "canonical_decision_ts",
    ):
        assert field_name in specification
    assert "runtime validator continues to accept an already formed handoff" in (
        specification
    )


def test_action_substitution_invalidates_authority_and_approval_bindings() -> None:
    """Pin V25's independently visible action-to-evidence mismatches."""
    by_id = {vector["vector_id"]: vector for vector in _vectors()}
    vector_25 = by_id["DTBH-V1-25"]
    handoff = vector_25["input"]

    assert (
        handoff["candidate"]["canonical_action"]["contract_id"]
        != handoff["authority_evidence"]["action_contract_id"]
    )
    assert (
        handoff["candidate"]["canonical_action"]["contract_id"]
        != handoff["human_approval_evidence"]["action_contract_id"]
    )
    assert vector_25["expected_reason_codes"] == [
        "HANDOFF_AUTHORITY_EVIDENCE_INVALID",
        "HANDOFF_APPROVAL_EVIDENCE_INVALID",
    ]
    assert "HANDOFF_CANDIDATE_HASH_MISMATCH" not in vector_25[
        "expected_reason_codes"
    ]
