"""Governance policy storage abstraction.

This module provides a file-based implementation that can be replaced with a
DB-backed store later without changing API handlers.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


DEFAULT_GOVERNANCE_POLICY: Dict[str, Any] = {
    "fuji_enabled": True,
    "risk_threshold": 0.55,
    "auto_stop_conditions": [
        "fuji_rejected",
        "security_violation_detected",
    ],
    "log_retention_days": 90,
    "audit_intensity": "standard",
}


class GovernancePolicyStore:
    """Abstract interface for governance policy persistence."""

    def load(self) -> Dict[str, Any]:
        """Return currently persisted policy data."""
        raise NotImplementedError

    def save(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        """Persist policy data and return the stored value."""
        raise NotImplementedError


class FileGovernancePolicyStore(GovernancePolicyStore):
    """Thread-safe JSON file store for governance policy."""

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._lock = threading.Lock()

    def load(self) -> Dict[str, Any]:
        """Load policy from disk, falling back to defaults on missing/invalid data."""
        with self._lock:
            if not self._file_path.exists():
                return deepcopy(DEFAULT_GOVERNANCE_POLICY)

            with open(self._file_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

            if not isinstance(payload, dict):
                return deepcopy(DEFAULT_GOVERNANCE_POLICY)

            merged = deepcopy(DEFAULT_GOVERNANCE_POLICY)
            merged.update(payload)
            return merged

    def save(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        """Write policy to disk atomically and return a merged snapshot."""
        with self._lock:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            merged = deepcopy(DEFAULT_GOVERNANCE_POLICY)
            merged.update(policy)

            tmp_path = self._file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as file_obj:
                json.dump(merged, file_obj, ensure_ascii=False, indent=2)

            tmp_path.replace(self._file_path)
            return merged
