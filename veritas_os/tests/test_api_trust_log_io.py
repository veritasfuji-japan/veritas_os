from __future__ import annotations

import json
import threading
from pathlib import Path

from veritas_os.api import trust_log_io


class _LoggerStub:
    def __init__(self) -> None:
        self.warning_calls: list[tuple] = []
        self.debug_calls: list[tuple] = []

    def warning(self, *args):
        self.warning_calls.append(args)

    def debug(self, *args, **kwargs):
        self.debug_calls.append((args, kwargs))


def test_load_logs_json_supports_dict_and_list_payload(tmp_path: Path) -> None:
    logger = _LoggerStub()
    log_json = tmp_path / "trust_log.json"

    log_json.write_text(json.dumps({"items": [{"request_id": "r1"}]}), encoding="utf-8")
    items = trust_log_io.load_logs_json(
        log_json,
        max_log_file_size=1024 * 1024,
        effective_log_paths=lambda: (tmp_path, log_json, tmp_path / "trust_log.jsonl"),
        logger=logger,
    )
    assert items == [{"request_id": "r1"}]

    log_json.write_text(json.dumps([{"request_id": "r2"}]), encoding="utf-8")
    items = trust_log_io.load_logs_json(
        log_json,
        max_log_file_size=1024 * 1024,
        effective_log_paths=lambda: (tmp_path, log_json, tmp_path / "trust_log.jsonl"),
        logger=logger,
    )
    assert items == [{"request_id": "r2"}]


def test_append_trust_log_entry_writes_jsonl_and_json(tmp_path: Path) -> None:
    logger = _LoggerStub()
    log_json = tmp_path / "trust_log.json"
    log_jsonl = tmp_path / "trust_log.jsonl"

    def _effective_paths() -> tuple[Path, Path, Path]:
        return tmp_path, log_json, log_jsonl

    def _load(path: Path | None) -> list:
        return trust_log_io.load_logs_json(
            path,
            max_log_file_size=1024 * 1024,
            effective_log_paths=_effective_paths,
            logger=logger,
        )

    def _save(path: Path, items: list) -> None:
        trust_log_io.save_json(
            path,
            items,
            has_atomic_io=False,
            atomic_write_json=None,
            secure_chmod_fn=lambda _path: None,
        )

    published: list[dict] = []
    trust_log_io.append_trust_log_entry(
        {"request_id": "req-1", "kind": "decision"},
        effective_log_paths=_effective_paths,
        has_atomic_io=False,
        atomic_append_line=None,
        load_logs_json_fn=_load,
        save_json_fn=_save,
        secure_chmod_fn=lambda _path: None,
        publish_event=lambda event_type, payload: published.append(
            {"event_type": event_type, "payload": payload}
        ),
        logger=logger,
        errstr=str,
        trust_log_lock=threading.Lock(),
    )

    lines = log_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["request_id"] == "req-1"

    aggregate = json.loads(log_json.read_text(encoding="utf-8"))
    assert aggregate["items"][0]["request_id"] == "req-1"
    assert published[0]["event_type"] == "trustlog.appended"


def test_write_shadow_decide_snapshot_creates_snapshot(tmp_path: Path) -> None:
    logger = _LoggerStub()
    shadow_dir = tmp_path / "DASH"

    trust_log_io.write_shadow_decide_snapshot(
        request_id="req-2",
        body={"context": {"query": "fallback query"}},
        chosen={"answer": "ok"},
        telos_score=0.75,
        fuji={"status": "allow"},
        effective_shadow_dir=lambda: shadow_dir,
        has_atomic_io=False,
        atomic_write_json=None,
        secure_chmod_fn=lambda _path: None,
        logger=logger,
        errstr=str,
    )

    files = list(shadow_dir.glob("decide_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["query"] == "fallback query"
    assert payload["fuji"] == "allow"
