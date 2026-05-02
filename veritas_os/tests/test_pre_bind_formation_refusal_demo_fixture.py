"""Mini proof fixture test for covered ``/v1/decide`` pre-bind formation refusal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from veritas_os.core.lineage_promotability import evaluate_lineage_promotability
from veritas_os.core.lineage_transition_refusal import evaluate_execution_intent_transition
from veritas_os.core.participation_detection import evaluate_pre_bind_structural_detection
from veritas_os.core.preservation_evaluator import evaluate_pre_bind_preservation

_REQUEST_FIXTURE = Path("examples/decide/pre_bind_formation_refusal_request.json")
_EXPECTED_SUBSET_FIXTURE = Path(
    "examples/decide/pre_bind_formation_refusal_expected_subset.json"
)
_HEADERS = {"X-API-Key": "test-key"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_expected_subset(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        assert key in actual
        actual_value = actual[key]
        if isinstance(expected_value, dict):
            assert isinstance(actual_value, dict)
            _assert_expected_subset(actual_value, expected_value)
            continue
        assert actual_value == expected_value


def _build_refusal_payload_from_request(request_payload: dict[str, Any]) -> dict[str, Any]:
    signal = request_payload["context"]["pre_bind_participation_signal"]
    detection = evaluate_pre_bind_structural_detection(signal)
    preservation = evaluate_pre_bind_preservation(
        participation_signal=signal,
        pre_bind_detection_summary=detection["pre_bind_detection_summary"],
    )
    lineage = evaluate_lineage_promotability(
        pre_bind_detection_summary=detection["pre_bind_detection_summary"],
        pre_bind_preservation_summary=preservation["pre_bind_preservation_summary"],
    )
    transition = evaluate_execution_intent_transition(lineage_promotability=lineage)

    return {
        "ok": True,
        "request_id": "req-mini-proof",
        "query": request_payload["query"],
        "lineage_promotability": lineage,
        "transition_refusal": transition,
        "actionability_status": "formation_transition_refused",
        "business_decision": "HOLD",
        "next_action": "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE",
        "human_review_required": True,
        "execution_intent_id": None,
        "bound_execution_intent_id": None,
        "bind_receipt_id": None,
        "bind_receipt": None,
    }


def _client_with_stubbed_pipeline(monkeypatch, payload: dict[str, Any]) -> TestClient:
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    from veritas_os.api import server as srv

    class _Pipeline:
        async def run_decide_pipeline(self, req, request):
            return payload

    monkeypatch.setattr(srv, "get_decision_pipeline", lambda: _Pipeline())
    return TestClient(srv.app, raise_server_exceptions=False)


def test_pre_bind_formation_refusal_demo_fixture_subset(monkeypatch) -> None:
    request_fixture = _load_json(_REQUEST_FIXTURE)
    expected_subset = _load_json(_EXPECTED_SUBSET_FIXTURE)

    payload = _build_refusal_payload_from_request(request_fixture)
    client = _client_with_stubbed_pipeline(monkeypatch, payload)
    response = client.post("/v1/decide", headers=_HEADERS, json=request_fixture)

    assert response.status_code == 200
    body = response.json()

    assert (
        body["lineage_promotability"]["promotability_status"] == "non_promotable"
    )
    assert (
        body["transition_refusal"]["transition_status"] == "structurally_refused"
    )
    assert body["transition_refusal"]["reason_code"] == "NON_PROMOTABLE_LINEAGE"
    assert body["actionability_status"] == "formation_transition_refused"
    assert body["business_decision"] == "HOLD"
    assert body["next_action"] == "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE"
    assert body["human_review_required"] is True
    assert body["execution_intent_id"] is None
    assert body["bind_receipt_id"] is None
    assert body["bind_receipt"] is None

    _assert_expected_subset(body, expected_subset)
