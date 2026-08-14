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

    This test-only coherence assertion is deliberately not a production handoff
    validator. Runtime validation remains future, separately reviewed work.
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
        assert by_id[vector_id]["expected_handoff_status"] == "INVALID"
        assert "HANDOFF_AUTHORITY_EVIDENCE_MISSING" in by_id[vector_id][
            "expected_reason_codes"
        ]
        assert by_id[vector_id]["forbidden_inference"]


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
