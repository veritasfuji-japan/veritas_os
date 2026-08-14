"""Coherence tests for the specification-only Decision-to-Bind contract."""

from __future__ import annotations

import json
from pathlib import Path

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


def _load_json(path: Path) -> dict[str, object]:
    """Load one repository-owned JSON specification artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _vectors() -> list[dict[str, object]]:
    """Return deterministic vectors in their filename order."""
    return [_load_json(path) for path in sorted(VECTOR_DIR.glob("vector-*.json"))]


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
