"""Additional replay coverage tests for pipeline replay helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.core import pipeline


class _BareDecideRequest:
    """Stub request type without ``model_validate`` to hit fallback path."""



def test_load_persisted_decision_skips_invalid_entries(tmp_path: Path, monkeypatch) -> None:
    """Loader should ignore malformed/non-dict snapshots and return matching payload."""
    invalid = tmp_path / "decide_invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")

    non_dict = tmp_path / "decide_list.json"
    non_dict.write_text(json.dumps(["unexpected"]), encoding="utf-8")

    payload = {"request_id": "req-1", "decision_id": "dec-1", "query": "ok"}
    valid = tmp_path / "decide_valid.json"
    valid.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(pipeline, "LOG_DIR", tmp_path)

    assert pipeline._load_persisted_decision("dec-1") == payload
    assert pipeline._load_persisted_decision("req-1") == payload


@pytest.mark.asyncio
async def test_replay_decision_handles_non_dict_replay_meta_and_save_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Replay should normalize malformed snapshot shapes and tolerate report save errors."""
    snapshot = {
        "request_id": "rid-42",
        "query": "What should we do?",
        "deterministic_replay": {
            "seed": 3,
            "temperature": 0,
            "request_body": ["not-a-dict"],
            "final_output": ["also-not-a-dict"],
        },
    }

    captured = {}

    async def _fake_run_decide_pipeline(req, _request):
        captured["req"] = req
        return {"decision": "allow", "meta": {"confidence": 0.9}}

    def _raise_value_error(*_args, **_kwargs):
        raise ValueError("simulated write failure")

    monkeypatch.setattr(pipeline, "_load_persisted_decision", lambda _did: snapshot)
    monkeypatch.setattr(pipeline, "run_decide_pipeline", _fake_run_decide_pipeline)
    monkeypatch.setattr(pipeline, "REPLAY_REPORT_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "DecideRequest", _BareDecideRequest)
    monkeypatch.setattr(pipeline, "_HAS_ATOMIC_IO", True)
    monkeypatch.setattr(pipeline, "_atomic_write_json", _raise_value_error)

    result = await pipeline.replay_decision("rid-42", mock_external_apis=False)

    assert result["match"] is False
    assert result["diff"]["changed"] is True
    assert result["replay_time_ms"] >= 1

    req = captured["req"]
    assert req["request_id"] == "rid-42"
    assert req["query"] == "What should we do?"
    assert req["seed"] == 3
    assert req["temperature"] == 0
    assert req["context"]["_replay_mode"] is True
    assert req["context"]["_mock_external_apis"] is False
