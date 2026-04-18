"""File-based governance repository implementation."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from veritas_os.governance.models import GovernancePolicyEventRecord
from veritas_os.governance.repository import GovernanceRepository

try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json

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
        with self._lock:
            if not self._policy_path.exists():
                return default_factory()
            try:
                with open(self._policy_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
                logger.warning("Failed to load governance policy: %s", exc)
                return default_factory()

    def save_policy(self, policy: dict[str, Any]) -> None:
        with self._lock:
            self._policy_path.parent.mkdir(parents=True, exist_ok=True)
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
        line = json.dumps(event.to_dict(), ensure_ascii=False)
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with open(self._history_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                self._trim_policy_history_locked()
        except Exception as exc:
            logger.warning("Failed to append governance policy history: %s", exc)

    def list_policy_history(self, *, limit: int, max_records: int) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, max_records))
        with self._lock:
            if not self._history_path.exists():
                return []
            try:
                lines = self._history_path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Failed to read governance policy history: %s", exc)
                return []

        records: list[dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
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
    ) -> None:
        self.save_policy(updated)
        self.append_policy_event(
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
    ) -> None:
        self.save_policy(restored)
        self.append_policy_event(
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
            lines = self._history_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if len(lines) <= self._policy_history_max:
                return

            trimmed = "".join(lines[-self._policy_history_max :])
            tmp = self._history_path.with_suffix(".tmp")
            tmp.write_text(trimmed, encoding="utf-8")
            tmp.replace(self._history_path)
        except Exception as exc:
            logger.warning("Failed to trim governance policy history: %s", exc)

    def trim_policy_history(self) -> None:
        """Trim history file to policy_history_max records."""
        with self._lock:
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
