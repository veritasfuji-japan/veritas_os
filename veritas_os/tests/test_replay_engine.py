from __future__ import annotations

import hashlib
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
            "model_version": "gpt-5-thinking",
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

    async def _fake_run(req, _request, **_kw):
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
            "model_version": "gpt-5-thinking",
            "external_dependency_versions": {
                "python_version": "3.12.0",
                "platform": "linux-x",
                "packages": {"openai": "1.0.0"},
            },
            "request_body": {"query": "hello", "context": {}},
            "final_output": {
                "decision": {"output": "allow", "answer": "ok"},
                "fuji": {"result": "allow", "status": "allow"},
                "value_scores": {"safety": 1.0},
                "evidence": [{"title": "X"}],
            },
        },
    }

    async def _fake_run(_req, _request, **_kw):
        return {
            "decision": {"output": "reject", "answer": "ng"},
            "fuji": {"result": "reject", "status": "reject"},
            "value_scores": {"safety": 0.2},
            "evidence": [{"title": "Y"}],
        }

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-5-thinking")

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
    assert payload["meta"]["external_dependency_versions"]["packages"]["openai"] == "1.0.0"


@pytest.mark.asyncio
async def test_run_replay_rejects_model_version_mismatch(monkeypatch, tmp_path: Path) -> None:
    snapshot = {
        "request_id": "dec-300",
        "query": "hello",
        "deterministic_replay": {
            "model_version": "gpt-4.1-mini",
            "request_body": {"query": "hello", "context": {}},
            "final_output": {},
        },
    }

    async def _fake_run(_req, _request, **_kw):
        return {}

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-5-thinking")

    with pytest.raises(ValueError, match="replay_model_version_mismatch"):
        await replay_engine.run_replay("dec-300", strict=True)


@pytest.mark.asyncio
async def test_run_replay_rejects_retrieval_checksum_mismatch(monkeypatch, tmp_path: Path) -> None:
    retrieval_snapshot = {"retrieved": [{"source": "memory"}], "web": {"hits": 1}}
    checksum = hashlib.sha256(
        json.dumps(retrieval_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    snapshot = {
        "request_id": "dec-301",
        "query": "hello",
        "deterministic_replay": {
            "model_version": "gpt-4.1-mini",
            "retrieval_snapshot": retrieval_snapshot,
            "retrieval_snapshot_checksum": checksum + "x",
            "request_body": {"query": "hello", "context": {}},
            "final_output": {},
        },
    }

    async def _fake_run(_req, _request, **_kw):
        return {}

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setenv("VERITAS_MODEL_NAME", "gpt-4.1-mini")

    with pytest.raises(ValueError, match="replay_retrieval_snapshot_checksum_mismatch"):
        await replay_engine.run_replay("dec-301", strict=True)


@pytest.mark.asyncio
async def test_run_replay_rejects_missing_model_version_by_default(
    monkeypatch, tmp_path: Path,
) -> None:
    snapshot = {
        "request_id": "dec-302",
        "query": "hello",
        "deterministic_replay": {
            "request_body": {"query": "hello", "context": {}},
            "final_output": {},
        },
    }

    async def _fake_run(_req, _request, **_kw):
        return {}

    monkeypatch.setattr(replay_engine.pipeline, "_load_persisted_decision", lambda _id: snapshot)
    monkeypatch.setattr(replay_engine.pipeline, "run_decide_pipeline", _fake_run)
    monkeypatch.setattr(replay_engine.pipeline, "REPLAY_REPORT_DIR", tmp_path)

    with pytest.raises(ValueError, match="replay_model_version_missing"):
        await replay_engine.run_replay("dec-302", strict=True)


def test_normalize_external_dependency_evidence_handles_invalid_shape() -> None:
    normalized = replay_engine._normalize_external_dependency_evidence(["bad"])
    assert normalized == {}

    normalized2 = replay_engine._normalize_external_dependency_evidence(
        {"python_version": 3.12, "platform": None, "packages": {"openai": 1}}
    )
    assert normalized2["python_version"] == "3.12"
    assert normalized2["platform"] == ""
    assert normalized2["packages"]["openai"] == "1"
