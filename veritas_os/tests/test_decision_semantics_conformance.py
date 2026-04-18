"""Decision semantics public-contract conformance tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from veritas_os.api.schemas import DecideResponse
from veritas_os.core.decision_semantics import (
    CANONICAL_GATE_DECISION_VALUES,
    GATE_DECISION_ALIAS_TO_CANONICAL,
)
from veritas_os.core.pipeline.pipeline_response import assemble_response
from veritas_os.core.pipeline.pipeline_types import PipelineContext
from veritas_os.scripts.expected_semantics_compare import compare_expected_semantics

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_SNAPSHOT_PATH = (
    REPO_ROOT / "veritas_os" / "tests" / "snapshots" / "decision_semantics_openapi_snapshot.json"
)


def _load_openapi_spec() -> dict[str, Any]:
    with (REPO_ROOT / "openapi.yaml").open("r", encoding="utf-8") as file_obj:
        return yaml.safe_load(file_obj)


def _extract_openapi_decision_contract() -> dict[str, Any]:
    spec = _load_openapi_spec()
    decide_properties = spec["components"]["schemas"]["DecideResponse"]["properties"]
    return {
        "gate_decision_enum": decide_properties["gate_decision"]["enum"],
        "gate_decision_examples": decide_properties["gate_decision"]["examples"],
        "business_decision_enum": decide_properties["business_decision"]["enum"],
        "human_review_required_type": decide_properties["human_review_required"]["type"],
        "decision_status_enum": decide_properties["decision_status"]["enum"],
    }


@pytest.mark.parametrize(
    "legacy_status, expected_gate",
    [
        ("allow", "proceed"),
        ("modify", "hold"),
        ("abstain", "hold"),
        ("rejected", "block"),
        ("block", "block"),
    ],
)
def test_public_api_emits_canonical_gate_values(legacy_status: str, expected_gate: str) -> None:
    """Public response payloads must emit canonical gate labels."""
    ctx = PipelineContext(
        request_id=f"req-gate-{legacy_status}",
        query="conformance",
        fuji_dict={"decision_status": legacy_status, "status": legacy_status},
        decision_status=legacy_status,
        context={},
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    assert payload["gate_decision"] == expected_gate
    assert payload["gate_decision"] in set(CANONICAL_GATE_DECISION_VALUES)


def test_forbidden_review_required_pairings_are_rejected() -> None:
    """REVIEW_REQUIRED and human review gate/flag coupling must be strict."""
    with pytest.raises(ValidationError, match="requires gate_decision=human_review_required"):
        DecideResponse.model_validate(
            {
                "gate_decision": "hold",
                "business_decision": "REVIEW_REQUIRED",
                "human_review_required": True,
            }
        )
    with pytest.raises(ValidationError, match="requires business_decision=REVIEW_REQUIRED"):
        DecideResponse.model_validate(
            {
                "gate_decision": "human_review_required",
                "business_decision": "HOLD",
                "human_review_required": True,
            }
        )


def test_openapi_decision_contract_matches_snapshot() -> None:
    """Decision semantics section of OpenAPI must remain frozen."""
    snapshot = json.loads(OPENAPI_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert _extract_openapi_decision_contract() == snapshot


def test_sample_expected_semantics_conform_to_response_schema() -> None:
    """Bundled sample expected semantics must validate against DecideResponse."""
    sample_paths = [
        REPO_ROOT / "veritas_os" / "sample_data" / "governance" / "financial_poc_questions.json",
        REPO_ROOT
        / "veritas_os"
        / "sample_data"
        / "governance"
        / "financial_regulatory_templates.json",
    ]
    expected_semantics_records: list[dict[str, Any]] = []

    poc_data = json.loads(sample_paths[0].read_text(encoding="utf-8"))
    expected_semantics_records.extend(
        [
            item["expected_semantics"]
            for item in poc_data
            if isinstance(item, dict) and isinstance(item.get("expected_semantics"), dict)
        ]
    )
    templates_data = json.loads(sample_paths[1].read_text(encoding="utf-8"))
    expected_semantics_records.extend(
        [
            item["expected_semantics"]
            for item in templates_data.get("templates", [])
            if isinstance(item, dict) and isinstance(item.get("expected_semantics"), dict)
        ]
    )

    assert expected_semantics_records, "No expected_semantics records found in sample data."
    for expected in expected_semantics_records:
        payload = {
            "gate_decision": expected.get("gate_decision", "unknown"),
            "business_decision": expected.get("business_decision", "HOLD"),
            "next_action": expected.get("next_action", "REVISE_AND_RESUBMIT"),
            "required_evidence": expected.get("required_evidence", []),
            "missing_evidence": expected.get("missing_evidence", []),
            "human_review_required": bool(expected.get("human_review_required", False)),
        }
        validated = DecideResponse.model_validate(payload)
        assert validated.gate_decision in set(CANONICAL_GATE_DECISION_VALUES)


def test_compare_helper_and_runtime_alias_maps_stay_consistent() -> None:
    """Compare helper assumptions must follow runtime canonical alias mapping."""
    for raw_gate in ("allow", "modify", "rejected", "abstain", "deny"):
        expected_payload = {
            "gate_decision": raw_gate,
            "business_decision": "HOLD",
            "required_evidence": [],
            "missing_evidence": [],
            "human_review_required": False,
        }
        actual_payload = {
            "gate_decision": GATE_DECISION_ALIAS_TO_CANONICAL[raw_gate],
            "business_decision": "HOLD",
            "required_evidence": [],
            "missing_evidence": [],
            "human_review_required": False,
        }
        assert compare_expected_semantics(expected_payload, actual_payload) == {}
