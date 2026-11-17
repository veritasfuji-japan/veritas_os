"""File-based governance repository implementation."""

from __future__ import annotations

import errno
import json
import logging
import os
import tempfile
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator

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
_HISTORY_READ_BLOCK_SIZE = 64 * 1024


def _reverse_history_lines(history: BinaryIO) -> Iterator[bytes]:
    """Yield lines newest-first, buffering only the current chunk and line."""
    position = history.seek(0, os.SEEK_END)
    fragments: list[bytes] = []
    while position:
        size = min(position, _HISTORY_READ_BLOCK_SIZE)
        position -= size
        history.seek(position)
        block = history.read(size)
        if len(block) != size:
            raise OSError("Governance history changed size during read")
        lines = block.split(b"\n")
        fragments.append(lines.pop())
        if lines:
            yield b"".join(reversed(fragments))
            yield from reversed(lines[1:])
            fragments = [lines[0]]
    if fragments:
        yield b"".join(reversed(fragments))


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

        content = json.dumps(policy, ensure_ascii=False, indent=2) + "\n"
        self._replace_text_fallback(self._policy_path, content)

        # Match the normal atomic writer's best-effort directory sync after
        # replacement. The updated policy is already visible at this point.
        try:
            self._sync_directory(self._policy_path.parent)
        except OSError as exc:
            logger.warning("Failed to sync governance policy directory: %s", exc)

    @staticmethod
    def _replace_text_fallback(path: Path, content: str) -> None:
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                tmp = Path(temp_file.name)
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            tmp.replace(path)
        except Exception:
            if tmp is not None:
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
        # A file fsync alone does not persist a newly created directory entry.
        # Sync the directory on retries too, since a previously failed sync
        # can leave the name visible in memory.
        self._sync_directory(self._history_path.parent)
        self._trim_policy_history_locked()

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                try:
                    os.fsync(directory_fd)
                except OSError as exc:
                    if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                        raise
                    logger.warning("Governance directory sync unsupported for %s: %s", directory, exc)
            finally:
                os.close(directory_fd)

    def list_policy_history(self, *, limit: int, max_records: int) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, max_records))
        records: list[dict[str, Any]] = []
        invalid = 0
        with self._lock:
            try:
                with self._history_path.open("rb") as history:
                    for line in _reverse_history_lines(history):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line.decode("utf-8"))
                        except (ValueError, RecursionError):
                            invalid += 1
                            continue
                        if not isinstance(record, dict):
                            invalid += 1
                            continue
                        records.append(record)
                        if len(records) >= bounded_limit:
                            break
            except FileNotFoundError:
                return []
            except OSError as exc:
                logger.warning("Failed to read governance policy history: %s", exc)
                return []
        if invalid:
            logger.warning("Skipped %d invalid governance policy history record(s) during read", invalid)
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
            # Count only complete JSON objects toward the retention limit.
            retained: deque[str] = deque(maxlen=self._policy_history_max or None)
            invalid = 0
            with self._history_path.open("rb") as history:
                scan_limit = self._policy_history_max + 1
                if sum(1 for _ in islice(history, scan_limit)) < scan_limit:
                    return
                history.seek(0)
                for line in history:
                    if not line.strip():
                        continue
                    try:
                        decoded = line.removesuffix(b"\n").decode("utf-8")
                        record = json.loads(decoded)
                    except (ValueError, RecursionError):
                        invalid += 1
                        continue
                    if isinstance(record, dict):
                        retained.append(decoded)
                    else:
                        invalid += 1
            if invalid:
                logger.warning(
                    "Skipped %d invalid governance policy history record(s) during trim", invalid
                )
            trimmed = "".join(line + "\n" for line in retained)
            if self._has_atomic_io:
                _atomic_write_text(self._history_path, trimmed)
                return

            self._replace_text_fallback(self._history_path, trimmed)
            self._sync_directory(self._history_path.parent)
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
