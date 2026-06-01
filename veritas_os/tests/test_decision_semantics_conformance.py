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


def test_restrictive_decision_precedence_pure_contract() -> None:
    """Decision precedence is machine-readable and fail-closed."""
    from veritas_os.core.decision_semantics import (
        decision_severity,
        resolve_decision_precedence,
    )

    assert decision_severity("deny") > decision_severity("hold")
    assert decision_severity("hold") > decision_severity("allow")
    assert resolve_decision_precedence("allow", "allow") == "allow"
    assert resolve_decision_precedence("allow", "hold") == "hold"
    assert resolve_decision_precedence("hold", "deny") == "deny"
    assert resolve_decision_precedence("approved", "rejected") == "rejected"
    assert resolve_decision_precedence("malformed_decision") == "block"
    assert resolve_decision_precedence("malformed_decision", output="gate") == "block"


@pytest.mark.parametrize(
    "fuji_decision, business_decision, expected_gate, expected_business",
    [
        ("allow", "HOLD", "hold", "HOLD"),
        ("deny", "APPROVE", "block", "DENY"),
        ("rejected", "APPROVED", "block", "DENY"),
        ("hold", "APPROVE", "hold", "HOLD"),
        ("malformed_decision", "APPROVE", "block", "DENY"),
    ],
)
def test_decision_path_conflicts_resolve_to_stricter_outcome(
    fuji_decision: str,
    business_decision: str,
    expected_gate: str,
    expected_business: str,
) -> None:
    """Gate/business/FUJI conflicts must converge on the stricter outcome."""
    ctx = PipelineContext(
        request_id=f"req-precedence-{fuji_decision}-{business_decision}",
        query="conformance",
        fuji_dict={"decision_status": fuji_decision, "status": fuji_decision},
        decision_status=fuji_decision,
        context={"business_decision": business_decision},
    )
    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )

    assert payload["gate_decision"] == expected_gate
    assert payload["business_decision"] == expected_business


@pytest.mark.parametrize("fuji_status", ["needs_human_review", "allow_with_warning"])
def test_known_fuji_review_statuses_are_not_fail_closed_blocks(fuji_status: str) -> None:
    """Known FUJI review/advisory statuses resolve to hold/review class."""
    from veritas_os.core.decision_semantics import (
        decision_severity,
        resolve_decision_precedence,
    )

    assert decision_severity(fuji_status) == decision_severity("hold")
    assert resolve_decision_precedence(fuji_status, output="gate") == "hold"
    assert resolve_decision_precedence(fuji_status, output="bind") == "escalate"


@pytest.mark.parametrize("raw_status", ["maybe", "unknown"])
def test_unknown_decision_statuses_still_fail_closed(raw_status: str) -> None:
    """Unknown or malformed decision strings remain fail-closed blocks."""
    from veritas_os.core.decision_semantics import resolve_decision_precedence

    assert resolve_decision_precedence(raw_status, output="gate") == "block"
    assert resolve_decision_precedence(raw_status, output="bind") == "block"


def test_review_required_with_missing_evidence_keeps_valid_review_pairing() -> None:
    """Manual review decisions must not emit invalid evidence-required pairing."""
    ctx = PipelineContext(
        request_id="req-review-required-with-missing-evidence",
        query="conformance",
        fuji_dict={"decision_status": "allow", "status": "allow"},
        decision_status="allow",
        context={
            "business_decision": "REVIEW_REQUIRED",
            "required_evidence": ["approval_ticket"],
            "satisfied_evidence": [],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    DecideResponse.model_validate(payload)

    assert payload["gate_decision"] == "human_review_required"
    assert payload["business_decision"] == "REVIEW_REQUIRED"
    assert payload["human_review_required"] is True
    assert payload["missing_evidence"] == ["approval_ticket"]
    assert payload["business_decision"] != "APPROVE"


def test_block_with_missing_evidence_surfaces_evidence_required() -> None:
    """Block gate still keeps evidence gaps visible as business state."""
    ctx = PipelineContext(
        request_id="req-block-missing-evidence",
        query="conformance",
        fuji_dict={"decision_status": "deny", "status": "deny"},
        decision_status="rejected",
        context={
            "required_evidence": ["approval_ticket"],
            "satisfied_evidence": [],
        },
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    DecideResponse.model_validate(payload)

    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "EVIDENCE_REQUIRED"
    assert payload["next_action"] == "COLLECT_REQUIRED_EVIDENCE"


def test_block_with_explicit_review_required_uses_valid_deny_pairing() -> None:
    """Block plus explicit review cannot emit invalid review-required coupling."""
    ctx = PipelineContext(
        request_id="req-block-review-required",
        query="conformance",
        fuji_dict={"decision_status": "deny", "status": "deny"},
        decision_status="rejected",
        context={"business_decision": "REVIEW_REQUIRED"},
    )

    payload = assemble_response(
        ctx,
        load_persona_fn=lambda: {},
        plan={"steps": [], "source": "test"},
    )
    DecideResponse.model_validate(payload)

    assert payload["gate_decision"] == "block"
    assert payload["business_decision"] == "DENY"
    assert payload["next_action"] == "DO_NOT_EXECUTE"
