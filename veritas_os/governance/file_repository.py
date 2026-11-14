"""File-based governance repository implementation."""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from veritas_os.governance.models import GovernancePolicyEventRecord
from veritas_os.governance.repository import (
    GovernanceHistoryWriteError,
    GovernanceRepository,
    GovernanceWriteConflictError,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json
    from veritas_os.core.atomic_io import atomic_write_text as _atomic_write_text

    _HAS_ATOMIC_IO = True
except ImportError:  # pragma: no cover
    _HAS_ATOMIC_IO = False

logger = logging.getLogger(__name__)


class FileGovernanceRepository(GovernanceRepository):
    """File-backed repository for governance policy state and history."""

    def __init__(
        self,
        *,
        policy_path: Path,
        history_path: Path,
        lock: threading.Lock,
        policy_history_max: int,
        has_atomic_io: bool | None = None,
    ) -> None:
        self._policy_path = policy_path
        self._history_path = history_path
        self._lock = lock
        self._policy_history_max = policy_history_max
        self._has_atomic_io = _HAS_ATOMIC_IO if has_atomic_io is None else has_atomic_io

    def get_current_policy(
        self,
        *,
        default_factory: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Use defaults on first initialization and reject unreadable policy state."""
        with self._lock:
            policy = self._read_policy_locked()
            return default_factory() if policy is None else policy

    def _read_policy_locked(self) -> dict[str, Any] | None:
        try:
            self._policy_path.lstat()
        except FileNotFoundError:
            return None
        except OSError:
            raise RuntimeError("Cannot inspect saved governance policy") from None

        try:
            with self._policy_path.open("r", encoding="utf-8") as policy_file:
                policy = json.load(policy_file)
        except (OSError, ValueError, RecursionError):
            raise RuntimeError("Cannot read saved governance policy") from None

        if not isinstance(policy, dict):
            raise RuntimeError("Saved governance policy must be a JSON object")
        return policy

    @contextmanager
    def _policy_write_lock(self) -> Iterator[None]:
        """Serialize compare-and-write across workers where flock is available."""
        with self._lock:
            self._policy_path.parent.mkdir(parents=True, exist_ok=True)
            if fcntl is None:
                yield
                return

            # The policy file is replaced on write, so lock a stable sidecar.
            lock_path = self._policy_path.with_name(self._policy_path.name + ".lock")
            with lock_path.open("ab") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield

    def _save_with_event(
        self,
        previous: dict[str, Any],
        updated: dict[str, Any],
        event: GovernancePolicyEventRecord,
    ) -> None:
        """Keep policy writes and their history appends in commit order."""
        from veritas_os.policy.governance_identity import compute_governance_digest

        with self._policy_write_lock():
            current = self._read_policy_locked()
            if current is not None and (
                compute_governance_digest(current) != compute_governance_digest(previous)
            ):
                raise GovernanceWriteConflictError("Current governance policy has changed")
            self._save_policy_locked(updated)
            try:
                self._append_policy_event_locked(event)
            except (OSError, ValueError, TypeError, RecursionError) as exc:
                raise GovernanceHistoryWriteError(
                    "GOVERNANCE_POLICY_HISTORY_WRITE_FAILED"
                ) from exc

    def save_policy(self, policy: dict[str, Any]) -> None:
        with self._policy_write_lock():
            self._save_policy_locked(policy)

    def _save_policy_locked(self, policy: dict[str, Any]) -> None:
        if self._has_atomic_io:
            _atomic_write_json(self._policy_path, policy, indent=2)
            return

        tmp = self._policy_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(policy, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self._policy_path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def append_policy_event(self, event: GovernancePolicyEventRecord) -> None:
        try:
            with self._policy_write_lock():
                self._append_policy_event_locked(event)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            logger.warning("Failed to append governance policy history: %s", exc)

    def _append_policy_event_locked(self, event: GovernancePolicyEventRecord) -> None:
        line = (json.dumps(event.to_dict(), ensure_ascii=False) + "\n").encode("utf-8")
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a+b") as history:
            history.seek(0, os.SEEK_END)
            if history.tell() > 0:
                history.seek(-1, os.SEEK_END)
                if history.read(1) != b"\n":
                    # A previous write may have stopped before the line delimiter.
                    line = b"\n" + line
            history.write(line)
            history.flush()
            os.fsync(history.fileno())
        self._trim_policy_history_locked()

    def list_policy_history(self, *, limit: int, max_records: int) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, max_records))
        with self._lock:
            if not self._history_path.exists():
                return []
            try:
                lines = self._history_path.read_bytes().split(b"\n")
            except OSError as exc:
                logger.warning("Failed to read governance policy history: %s", exc)
                return []

        records: list[dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (ValueError, RecursionError):
                continue
            if not isinstance(record, dict):
                continue
            records.append(record)
            if len(records) >= bounded_limit:
                break
        return records

    def update_policy(
        self,
        *,
        previous: dict[str, Any],
        updated: dict[str, Any],
        proposer: str,
        approvers: list[str],
        event_type: str,
        approval_records: list[dict[str, str]] | None = None,
        reason: str = "",
    ) -> None:
        del approval_records, reason
        self._save_with_event(
            previous,
            updated,
            self._build_event(
                previous=previous,
                updated=updated,
                proposer=proposer,
                approvers=approvers,
                event_type=event_type,
            )
        )

    def rollback_policy(
        self,
        *,
        previous: dict[str, Any],
        restored: dict[str, Any],
        proposer: str,
        approvers: list[str],
        approval_records: list[dict[str, str]] | None = None,
        reason: str = "",
    ) -> None:
        del approval_records, reason
        self._save_with_event(
            previous,
            restored,
            self._build_event(
                previous=previous,
                updated=restored,
                proposer=proposer,
                approvers=approvers,
                event_type="rollback",
            )
        )

    def _trim_policy_history_locked(self) -> None:
        try:
            if not self._history_path.exists():
                return
            lines = self._history_path.read_bytes().split(b"\n")
            if lines[-1] == b"":
                lines.pop()
            if len(lines) <= self._policy_history_max:
                return

            # Count only complete JSON objects toward the retention limit.
            retained = []
            for line in lines:
                try:
                    decoded = line.decode("utf-8")
                    record = json.loads(decoded)
                except (ValueError, RecursionError):
                    continue
                if isinstance(record, dict):
                    retained.append(decoded)
            trimmed = "".join(line + "\n" for line in retained[-self._policy_history_max :])
            if self._has_atomic_io:
                _atomic_write_text(self._history_path, trimmed)
                return

            tmp = self._history_path.with_name(self._history_path.name + ".tmp")
            try:
                with tmp.open("w", encoding="utf-8") as history:
                    history.write(trimmed)
                    history.flush()
                    os.fsync(history.fileno())
                tmp.replace(self._history_path)
            except OSError:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
        except Exception as exc:
            logger.warning("Failed to trim governance policy history: %s", exc)

    def trim_policy_history(self) -> None:
        """Trim history file to policy_history_max records."""
        with self._policy_write_lock():
            self._trim_policy_history_locked()

    def _build_event(
        self,
        *,
        previous: dict[str, Any],
        updated: dict[str, Any],
        proposer: str,
        approvers: list[str],
        event_type: str,
    ) -> GovernancePolicyEventRecord:
        try:
            from veritas_os.policy.governance_identity import compute_governance_digest

            prev_digest = compute_governance_digest(previous)
            new_digest = compute_governance_digest(updated)
        except Exception:
            prev_digest = ""
            new_digest = ""

        return GovernancePolicyEventRecord(
            changed_at=updated.get("updated_at", datetime.now(timezone.utc).isoformat()),
            changed_by=updated.get("updated_by", "unknown"),
            proposer=proposer or updated.get("updated_by", "unknown"),
            approvers=approvers,
            event_type=event_type,
            previous_version=previous.get("version"),
            new_version=updated.get("version"),
            previous_digest=prev_digest,
            new_digest=new_digest,
            previous_policy=previous,
            new_policy=updated,
        )
