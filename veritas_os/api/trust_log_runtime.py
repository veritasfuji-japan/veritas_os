from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from veritas_os.api.trust_log_io import (
    append_trust_log_entry,
    load_logs_json,
    save_json,
    secure_chmod,
    write_shadow_decide_snapshot,
)


class TrustLogRuntime:
    """Runtime helpers for trust-log persistence within the API server.

    This class centralizes aggregate JSON loading, JSONL persistence,
    permission hardening, and shadow snapshot writes so that `server.py`
    can keep only thin compatibility wrappers.
    """

    def __init__(
        self,
        *,
        max_log_file_size: int,
        effective_log_paths: Callable[[], tuple[Path, Path, Path]],
        effective_shadow_dir: Callable[[], Path],
        has_atomic_io: bool,
        atomic_write_json: Optional[Callable[..., None]],
        atomic_append_line: Optional[Callable[..., None]],
        logger: Any,
        errstr: Callable[[Exception], str],
        trust_log_lock: Optional[Any] = None,
        publish_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        self.max_log_file_size = max_log_file_size
        self.effective_log_paths = effective_log_paths
        self.effective_shadow_dir = effective_shadow_dir
        self.has_atomic_io = has_atomic_io
        self.atomic_write_json = atomic_write_json
        self.atomic_append_line = atomic_append_line
        self.logger = logger
        self.errstr = errstr
        self.trust_log_lock = trust_log_lock or threading.Lock()
        self.publish_event = publish_event or self._noop_publish_event

    def load_logs_json(self, path: Optional[Path] = None) -> list:
        """Load trust-log aggregate JSON with server compatibility behavior."""
        return load_logs_json(
            path,
            max_log_file_size=self.max_log_file_size,
            effective_log_paths=self.effective_log_paths,
            logger=self.logger,
        )

    def secure_chmod(self, path: Path) -> None:
        """Apply restrictive 0600 permissions to a sensitive artifact."""
        secure_chmod(path, logger=self.logger, errstr=self.errstr)

    def save_json(self, path: Path, items: list) -> None:
        """Persist the aggregate trust-log JSON document."""
        save_json(
            path,
            items,
            has_atomic_io=self.has_atomic_io,
            atomic_write_json=self.atomic_write_json,
            secure_chmod_fn=self.secure_chmod,
        )

    def append_trust_log(self, entry: Dict[str, Any]) -> None:
        """Append trust-log records and emit the SSE event best-effort."""
        append_trust_log_entry(
            entry,
            effective_log_paths=self.effective_log_paths,
            has_atomic_io=self.has_atomic_io,
            atomic_append_line=self.atomic_append_line,
            load_logs_json_fn=self.load_logs_json,
            save_json_fn=self.save_json,
            secure_chmod_fn=self.secure_chmod,
            publish_event=self.publish_event,
            logger=self.logger,
            errstr=self.errstr,
            trust_log_lock=self.trust_log_lock,
        )

    def write_shadow_decide(
        self,
        request_id: str,
        body: Dict[str, Any],
        chosen: Dict[str, Any],
        telos_score: float,
        fuji: Optional[Dict[str, Any]],
    ) -> None:
        """Persist a shadow `/decide` snapshot for replay and audit workflows."""
        write_shadow_decide_snapshot(
            request_id,
            body,
            chosen,
            telos_score,
            fuji,
            effective_shadow_dir=self.effective_shadow_dir,
            has_atomic_io=self.has_atomic_io,
            atomic_write_json=self.atomic_write_json,
            secure_chmod_fn=self.secure_chmod,
            logger=self.logger,
            errstr=self.errstr,
        )

    @staticmethod
    def _noop_publish_event(_event_type: str, _payload: Dict[str, Any]) -> None:
        """Default event publisher used by tests that do not wire SSE."""

