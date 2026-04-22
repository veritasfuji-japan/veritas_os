"""Reusable bind adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from veritas_os.policy.bind_artifacts import ExecutionIntent


class BindAdapterContract(ABC):
    """Abstract bind adapter contract for bind-core adjudication."""

    @abstractmethod
    def snapshot(self) -> Any:
        """Capture current target state before bind execution."""

    @abstractmethod
    def fingerprint_state(self, snapshot: Any) -> str:
        """Return deterministic fingerprint of a state snapshot."""

    @abstractmethod
    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Return bind-time authority validity."""

    @abstractmethod
    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        """Return bind-time constraint status map."""

    @abstractmethod
    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Return runtime risk admissibility signal."""

    @abstractmethod
    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Apply staged change to target."""

    @abstractmethod
    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Verify postconditions after apply."""

    @abstractmethod
    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Revert or compensate using pre-apply snapshot."""

    @abstractmethod
    def describe_target(self) -> str:
        """Return short human-readable target description."""

    def build_idempotency_key(self, intent: ExecutionIntent) -> str:
        """Return idempotency key for dedupe/replay detection.

        Adapters may override this when intent id alone is insufficient.
        """
        del intent
        return ""
