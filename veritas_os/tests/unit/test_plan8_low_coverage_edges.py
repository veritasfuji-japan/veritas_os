"""Edge-case tests for low-coverage modules in plan item #8."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_gate as pg
from veritas_os.core.pipeline import pipeline_response as pr


@dataclass
class _DummyPipeline:
    """Minimal replay pipeline stub used by replay endpoint tests."""

    seen_mock_external_apis: bool | None = None

    async def replay_decision(
        self,
        *,
        decision_id: str,
        mock_external_apis: bool,
    ) -> dict[str, Any]:
        self.seen_mock_external_apis = mock_external_apis
        return {
            "decision_id": decision_id,
            "mock_external_apis": mock_external_apis,
        }


class _BrokenQueryParams:
    def get(self, _key: str) -> str:
        raise RuntimeError("query params unavailable")


class _DummyRequest:
    query_params = _BrokenQueryParams()


@pytest.mark.anyio
async def test_replay_decision_endpoint_query_params_error_defaults_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When query param access fails, replay endpoint should fail closed to True."""
    dummy_pipeline = _DummyPipeline()

    class _DummyServer:
        @staticmethod
        def get_decision_pipeline() -> _DummyPipeline:
            return dummy_pipeline

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    out = await rd.replay_decision_endpoint("dec-1", _DummyRequest())

    assert out["decision_id"] == "dec-1"
    assert out["mock_external_apis"] is True
    assert dummy_pipeline.seen_mock_external_apis is True


def test_finalize_evidence_invalid_payload_falls_back_to_empty_list() -> None:
    """Invalid evidence payload shapes should degrade to empty evidence safely."""

    class _BadIterable:
        def __iter__(self):
            raise TypeError("bad iterable")

    payload: dict[str, Any] = {"evidence": _BadIterable()}
    pr.finalize_evidence(payload, web_evidence=[], evidence_max=5)

    assert payload["evidence"] == []


def test_allow_prob_handles_invalid_predict_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid gate prediction payloads should map to a safe default probability."""
    monkeypatch.setattr(pg, "predict_gate_label", lambda _text: "not-a-dict")

    assert pg._allow_prob("sample") == 0.0


def test_schedule_rate_bucket_cleanup_logs_and_reschedules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler keeps running even when a cleanup pass raises an exception."""

    class _DummyTimer:
        def __init__(self, interval: float, callback: Any):
            self.interval = interval
            self.callback = callback
            self.daemon = False
            self.started = False

        def start(self) -> None:
            self.started = True

        def cancel(self) -> None:
            self.started = False

    created: list[_DummyTimer] = []

    def _timer_factory(interval: float, callback: Any) -> _DummyTimer:
        timer = _DummyTimer(interval, callback)
        created.append(timer)
        return timer

    monkeypatch.setattr(rl, "_cleanup_rate_bucket", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(rl.threading, "Timer", _timer_factory)

    old_timer = rl._rate_cleanup_timer
    try:
        rl._rate_cleanup_timer = object()
        rl._schedule_rate_bucket_cleanup()
    finally:
        rl._rate_cleanup_timer = old_timer

    assert len(created) == 1
    assert created[0].interval == rl._RATE_CLEANUP_INTERVAL
    assert created[0].started is True
