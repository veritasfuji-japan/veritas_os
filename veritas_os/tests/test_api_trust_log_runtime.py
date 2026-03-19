from __future__ import annotations

import json
import logging
from pathlib import Path

from veritas_os.api.trust_log_runtime import TrustLogRuntime


class _PublishRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, payload: dict) -> None:
        self.calls.append((event_type, payload))


def _build_runtime(tmp_path: Path, publish_event=None) -> TrustLogRuntime:
    log_dir = tmp_path / "logs"
    shadow_dir = tmp_path / "shadow"
    log_json = log_dir / "trust_log.json"
    log_jsonl = log_dir / "trust_log.jsonl"
    return TrustLogRuntime(
        max_log_file_size=1024 * 1024,
        effective_log_paths=lambda: (log_dir, log_json, log_jsonl),
        effective_shadow_dir=lambda: shadow_dir,
        has_atomic_io=False,
        atomic_write_json=None,
        atomic_append_line=None,
        logger=logging.getLogger("test.trust_log_runtime"),
        errstr=str,
        publish_event=publish_event,
    )


def test_load_logs_json_without_path_uses_effective_log_path(tmp_path: Path) -> None:
    runtime = _build_runtime(tmp_path)
    _, log_json, _ = runtime.effective_log_paths()
    log_json.parent.mkdir(parents=True, exist_ok=True)
    log_json.write_text(json.dumps({"items": [{"id": 1}]}), encoding="utf-8")

    assert runtime.load_logs_json() == [{"id": 1}]


def test_append_trust_log_persists_jsonl_and_aggregate_json(tmp_path: Path) -> None:
    recorder = _PublishRecorder()
    runtime = _build_runtime(tmp_path, publish_event=recorder)
    entry = {"request_id": "req-1", "kind": "decision", "status": "allow"}

    runtime.append_trust_log(entry)

    log_dir, log_json, log_jsonl = runtime.effective_log_paths()
    assert log_dir.exists()
    assert log_jsonl.read_text(encoding="utf-8").strip() == json.dumps(
        entry,
        ensure_ascii=False,
    )
    assert runtime.load_logs_json(log_json)[-1] == entry
    assert recorder.calls == [
        ("trustlog.appended", {"request_id": "req-1", "kind": "decision"})
    ]


def test_append_trust_log_skips_unreadable_aggregate_json(tmp_path: Path) -> None:
    """Unreadable aggregate JSON must not be overwritten during append."""
    recorder = _PublishRecorder()
    runtime = _build_runtime(tmp_path, publish_event=recorder)
    entry = {"request_id": "req-2", "kind": "decision", "status": "allow"}
    _, log_json, log_jsonl = runtime.effective_log_paths()
    log_json.parent.mkdir(parents=True, exist_ok=True)
    log_json.write_text("{broken json", encoding="utf-8")

    runtime.append_trust_log(entry)

    assert log_json.read_text(encoding="utf-8") == "{broken json"
    assert log_jsonl.read_text(encoding="utf-8").strip() == json.dumps(
        entry,
        ensure_ascii=False,
    )
    assert recorder.calls == []


def test_load_logs_json_result_marks_unreadable_payload(tmp_path: Path) -> None:
    """Structured load results must distinguish unreadable aggregate JSON."""
    runtime = _build_runtime(tmp_path)
    _, log_json, _ = runtime.effective_log_paths()
    log_json.parent.mkdir(parents=True, exist_ok=True)
    log_json.write_text("{broken json", encoding="utf-8")

    result = runtime.load_logs_json_result(log_json)

    assert result.status == "unreadable"
    assert result.items == []
    assert result.error


def test_write_shadow_decide_creates_snapshot_file(tmp_path: Path) -> None:
    runtime = _build_runtime(tmp_path)

    runtime.write_shadow_decide(
        request_id="req-shadow",
        body={"query": "hello"},
        chosen={"decision": "allow"},
        telos_score=0.75,
        fuji={"status": "ok"},
    )

    shadow_dir = runtime.effective_shadow_dir()
    files = list(shadow_dir.glob("decide_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["request_id"] == "req-shadow"
    assert payload["query"] == "hello"
    assert payload["fuji"] == "ok"


def test_server_wrappers_follow_monkeypatched_paths(monkeypatch, tmp_path: Path) -> None:
    from veritas_os.api import server

    shadow_dir = tmp_path / "shadow-wrapper"
    monkeypatch.setattr(
        server,
        "_effective_log_paths",
        lambda: (tmp_path, tmp_path / "wrapper.json", tmp_path / "wrapper.jsonl"),
    )
    monkeypatch.setattr(server, "_effective_shadow_dir", lambda: shadow_dir)

    server.append_trust_log({"request_id": "req-wrapper", "kind": "decision"})
    server.write_shadow_decide(
        request_id="req-wrapper",
        body={"query": "compat"},
        chosen={"decision": "allow"},
        telos_score=1.0,
        fuji={"status": "ok"},
    )

    assert (tmp_path / "wrapper.jsonl").exists()
    assert len(list(shadow_dir.glob("decide_*.json"))) == 1
