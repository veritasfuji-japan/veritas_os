"""Governance policy persistence helpers.

The initial implementation uses a local JSON file so operations stay lightweight.
Design keeps I/O logic isolated to ease future migration to DB-backed storage.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

from pydantic import ValidationError

from veritas_os.api.schemas import GovernancePolicy

_DEFAULT_POLICY: Dict[str, Any] = {
    "fuji_enabled": True,
    "risk_threshold": 0.65,
    "auto_stop_conditions": [
        "critical_fuji_violation",
        "trust_chain_break",
    ],
    "log_retention_days": 180,
    "audit_intensity": "standard",
}


class GovernancePolicyStore:
    """Thread-safe local-file store for governance policy."""

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._lock = threading.Lock()

    def _ensure_parent(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def load_policy(self) -> GovernancePolicy:
        """Load and validate policy from disk or return defaults."""
        with self._lock:
            if not self._file_path.exists():
                return GovernancePolicy.model_validate(_DEFAULT_POLICY)

            try:
                payload = json.loads(self._file_path.read_text(encoding="utf-8"))
                return GovernancePolicy.model_validate(payload)
            except (json.JSONDecodeError, ValidationError):
                return GovernancePolicy.model_validate(_DEFAULT_POLICY)

    def save_policy(self, policy: GovernancePolicy) -> GovernancePolicy:
        """Persist policy atomically and return the saved model."""
        with self._lock:
            self._ensure_parent()
            tmp_path = self._file_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(policy.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._file_path)
            return policy
