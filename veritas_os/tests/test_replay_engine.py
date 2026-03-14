from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from veritas_os.replay import replay_engine


def test_pipeline_version_returns_unknown_on_expected_subprocess_failures(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_PIPELINE_VERSION", raising=False)
    def _raise_called_process_error(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["git"])

    monkeypatch.setattr(replay_engine.subprocess, "check_output", _raise_called_process_error)

    assert replay_engine._pipeline_version() == "unknown"




def test_pipeline_version_prefers_env_override(monkeypatch) -> None:
    """Environment override should be used before git command lookup."""
    monkeypatch.setenv("VERITAS_PIPELINE_VERSION", "ci-sha-123")

    def _raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("should_not_run")

    monkeypatch.setattr(replay_engine.subprocess, "check_output", _raise_runtime_error)

    assert replay_engine._pipeline_version() == "ci-sha-123"

def test_pipeline_version_does_not_swallow_unexpected_errors(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_PIPELINE_VERSION", raising=False)
    def _raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(replay_engine.subprocess, "check_output", _raise_runtime_error)

    with pytest.raises(RuntimeError):
        replay_engine._pipeline_version()


@pytest.mark.asyncio
async def test_run_replay_strict_mode_skips_tools_and_matches(monkeypatch, tmp_path: Path) -> None:
    snapshot = {
        "request_id": "dec-100",
        "query": "hello",
        "deterministic_replay": {
            "seed": 42,
            "temperature": 0,
            "request_body": {"query": "hello", "context": {"user_id": "u1"}},
            "final_output": {
                "decision": {"output": "allow", "answer": "ok"},
                "fuji": {"result": "allow", "status": "allow"},
                "value_scores": {"safety": 0.9},
                "evidence": [{"id": "2", "title": "B"}, {"id": "1", "title": "A"}],
            },
        },
    }

    captured = {}

    async def _fake_run(req, _request):
        body = req.model_dump()
        captured["temperature"] = body.get("temperature")
        captured["seed"] = body.get("seed")
        captured["mock_external"] = body.get("context", {}).get("_mock_external_apis")
        return {
            "decision": {"output": "allow", "answer": "ok"},
            "fuji": {"result": "allow", "status": "allow"},
            "value_scores": {"safety": 0.9},
            "evidence": [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}],
        }

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setenv("VERITAS_REPLAY_STRICT", "1")

    result = await replay_engine.run_replay("dec-100")

    assert result.match is True
    assert captured["temperature"] == 0
    assert captured["seed"] == 42
    assert captured["mock_external"] is True
    reports = list(tmp_path.glob("replay_dec-100_*.json"))
    assert len(reports) == 1


@pytest.mark.asyncio
async def test_run_replay_writes_expected_diff_schema(monkeypatch, tmp_path: Path) -> None:
    snapshot = {
        "request_id": "dec-200",
        "query": "hello",
        "deterministic_replay": {
            "request_body": {"query": "hello", "context": {}},
            "final_output": {
                "decision": {"output": "allow", "answer": "ok"},
                "fuji": {"result": "allow", "status": "allow"},
                "value_scores": {"safety": 1.0},
                "evidence": [{"title": "X"}],
            },
        },
    }

    async def _fake_run(_req, _request):
        return {
            "decision": {"output": "reject", "answer": "ng"},
            "fuji": {"result": "reject", "status": "reject"},
            "value_scores": {"safety": 0.2},
            "evidence": [{"title": "Y"}],
        }

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)

    result = await replay_engine.run_replay("dec-200", strict=False)

    assert result.match is False
    assert "decision" in result.diff["fields_changed"]
    assert "before" in result.diff
    assert "after" in result.diff

    report_path = Path(result.replay_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["decision_id"] == "dec-200"
    assert "meta" in payload
    assert "pipeline_version" in payload["meta"]
