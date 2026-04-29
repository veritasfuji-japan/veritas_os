"""HTTP-level canonical pre-bind E2E tests for ``/v1/decide``."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from veritas_os.core.pipeline.governance_layers import assemble_governance_public_fields

_BIND_SENTINEL = {
    "bind_outcome": "ESCALATED",
    "bind_reason_code": "AUTHORITY_INSUFFICIENT",
    "bind_failure_reason": "authority evidence missing",
}

_FIXTURE_DIR = Path("veritas_os/tests/fixtures/pre_bind")
_GOLDEN_DIR = Path("veritas_os/tests/golden/pre_bind")
_HEADERS = {"X-API-Key": "test-key"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_payload(case_id: str, include_pre_bind: bool = True) -> dict[str, Any]:
    fixture = _load_json(_FIXTURE_DIR / f"{case_id}.json")
    payload: dict[str, Any] = {
        "ok": True,
        "error": None,
        "request_id": f"req-{case_id}",
        "query": "canonical pre-bind http e2e",
        "chosen": {"id": "alt-1", "title": "Execute canonical verification"},
        "alternatives": [{"id": "alt-1", "title": "Execute canonical verification"}],
        "evidence": [],
        "critique": {"ok": True, "findings": []},
        "debate": [],
        "telos_score": 0.5,
        "fuji": {"decision_status": "allow"},
        "gate": {"risk": 0.0, "telos_score": 0.5, "decision_status": "allow", "reason": None, "modifications": []},
        "values": {"scores": {}, "total": 0.0, "top_factors": [], "rationale": "stub"},
        "persona": {},
        "version": "test",
        "decision_status": "allow",
        "rejection_reason": None,
        "extras": {},
        "trust_log": None,
        **_BIND_SENTINEL,
    }
    if include_pre_bind:
        golden = _load_json(_GOLDEN_DIR / f"{case_id}_golden.json")
        snapshot = assemble_governance_public_fields(
            SimpleNamespace(
                participation_signal=fixture["participation_signal"],
                pre_bind_detection={
                    "pre_bind_detection_summary": golden["pre_bind_detection_summary"],
                    "pre_bind_detection_detail": golden["pre_bind_detection_detail"],
                },
                pre_bind_preservation={
                    "pre_bind_preservation_summary": golden["pre_bind_preservation_summary"],
                    "pre_bind_preservation_detail": golden["pre_bind_preservation_detail"],
                },
            )
        )
        payload.update(snapshot)
    return payload




def _assert_bind_family_regression_guard(body: dict[str, Any]) -> None:
    """Bind family fields must remain unchanged even with additive pre-bind fields."""
    for key, expected in _BIND_SENTINEL.items():
        assert body[key] == expected


def _assert_pre_bind_parity_with_golden(body: dict[str, Any], case_id: str) -> None:
    """HTTP response should preserve canonical state/rationale from golden assets."""
    golden = _load_json(_GOLDEN_DIR / f"{case_id}_golden.json")

    assert body["pre_bind_detection_summary"]["participation_state"] == (
        golden["pre_bind_detection_summary"]["participation_state"]
    )
    assert body["pre_bind_preservation_summary"]["preservation_state"] == (
        golden["pre_bind_preservation_summary"]["preservation_state"]
    )
    assert body["pre_bind_detection_summary"]["concise_rationale"] == (
        golden["pre_bind_detection_summary"]["concise_rationale"]
    )
    assert body["pre_bind_preservation_summary"]["concise_rationale"] == (
        golden["pre_bind_preservation_summary"]["concise_rationale"]
    )

def _client_with_stubbed_pipeline(monkeypatch, payload: dict[str, Any]) -> TestClient:
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    from veritas_os.api import server as srv

    class _Pipeline:
        async def run_decide_pipeline(self, req, request):
            return payload

    monkeypatch.setattr(srv, "get_decision_pipeline", lambda: _Pipeline())
    return TestClient(srv.app, raise_server_exceptions=False)


def test_decide_http_canonical_case_a_informative_open(monkeypatch) -> None:
    case_id = "pre_bind_case_informative_open"
    client = _client_with_stubbed_pipeline(monkeypatch, _build_payload(case_id))
    response = client.post("/v1/decide", headers=_HEADERS, json={"query": "case-a"})

    assert response.status_code == 200
    body = response.json()
    assert body["participation_signal"]["participation_admissibility"] in {"admissible", "review_required", "unknown"}
    _assert_pre_bind_parity_with_golden(body, case_id)
    assert "aggregate_index" in body["pre_bind_detection_detail"]
    assert body["pre_bind_preservation_detail"]["detection_context"]["participation_state"] == "informative"
    _assert_bind_family_regression_guard(body)


def test_decide_http_canonical_case_b_participatory_degrading(monkeypatch) -> None:
    case_id = "pre_bind_case_participatory_degrading"
    client = _client_with_stubbed_pipeline(monkeypatch, _build_payload(case_id))
    response = client.post("/v1/decide", headers=_HEADERS, json={"query": "case-b"})

    assert response.status_code == 200
    body = response.json()
    _assert_pre_bind_parity_with_golden(body, case_id)
    assert "aggregate_index" in body["pre_bind_detection_detail"]
    assert body["pre_bind_preservation_detail"]["detection_context"]["participation_state"] == "participatory"
    assert "primary_contributing_signals" in body["pre_bind_detection_summary"]
    _assert_bind_family_regression_guard(body)


def test_decide_http_canonical_case_c_decision_shaping_collapsed(monkeypatch) -> None:
    case_id = "pre_bind_case_decision_shaping_collapsed"
    client = _client_with_stubbed_pipeline(monkeypatch, _build_payload(case_id))
    response = client.post("/v1/decide", headers=_HEADERS, json={"query": "case-c"})

    assert response.status_code == 200
    body = response.json()
    _assert_pre_bind_parity_with_golden(body, case_id)
    assert "aggregate_index" in body["pre_bind_detection_detail"]
    assert body["pre_bind_preservation_detail"]["detection_context"]["participation_state"] == "decision_shaping"
    assert body["pre_bind_preservation_detail"]["detection_context"]["participation_state"] == "decision_shaping"
    _assert_bind_family_regression_guard(body)


def test_decide_http_pre_bind_optionality_absent_is_backward_compatible(monkeypatch) -> None:
    client = _client_with_stubbed_pipeline(
        monkeypatch,
        _build_payload("pre_bind_case_informative_open", include_pre_bind=False),
    )
    response = client.post("/v1/decide", headers=_HEADERS, json={"query": "legacy"})

    assert response.status_code == 200
    body = response.json()
    _assert_bind_family_regression_guard(body)
    assert body["pre_bind_detection_summary"] is None
    assert body["pre_bind_detection_detail"] is None
    assert body["pre_bind_preservation_summary"] is None
    assert body["pre_bind_preservation_detail"] is None
