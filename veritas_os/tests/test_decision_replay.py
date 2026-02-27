from __future__ import annotations

from pathlib import Path

import pytest

from veritas_os.core import pipeline


@pytest.mark.asyncio
async def test_replay_decision_returns_not_found_when_snapshot_missing() -> None:
    result = await pipeline.replay_decision("missing-id")

    assert result["match"] is False
    assert result["diff"]["error"] == "decision_not_found"
    assert result["replay_time_ms"] >= 1


@pytest.mark.asyncio
async def test_replay_decision_generates_report(monkeypatch, tmp_path: Path) -> None:
    snapshot = {
        "request_id": "dec-123",
        "query": "hello",
        "deterministic_replay": {
            "seed": 7,
            "temperature": 0,
            "request_body": {"query": "hello", "context": {"user_id": "u1"}},
            "final_output": {"decision": "allow", "meta": {"x": 1}},
        },
    }

    async def _fake_run_decide_pipeline(req, request):
        return {"decision": "allow", "meta": {"x": 1}}

    monkeypatch.setattr(pipeline, "_load_persisted_decision", lambda _: snapshot)
    monkeypatch.setattr(pipeline, "run_decide_pipeline", _fake_run_decide_pipeline)
    monkeypatch.setattr(pipeline, "REPLAY_REPORT_DIR", tmp_path)

    result = await pipeline.replay_decision("dec-123")

    assert result["match"] is True
    assert result["diff"]["changed"] is False
    assert result["replay_time_ms"] >= 1
    reports = list(tmp_path.glob("replay_dec-123_*.json"))
    assert reports


def test_build_replay_diff_detects_changes() -> None:
    original = {"decision": "allow", "meta": {"status": "ok"}}
    replayed = {"decision": "reject", "meta": {"status": "ok"}}

    diff = pipeline._build_replay_diff(original, replayed)

    assert diff["changed"] is True
    assert "decision" in diff["keys"]
