"""Concrete bind-boundary adapters for production-adjacent operations.

This module provides one real adapter that promotes an active policy bundle
pointer in local governance operations. The adapter is file-based, deterministic,
and supports explicit rollback via snapshot restoration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from veritas_os.core.atomic_io import atomic_write_json
from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.security.hash import sha256_of_canonical_json


@dataclass
class GovernancePolicyUpdateAdapter(BindAdapterContract):
    """Bind adapter for governed policy update execution.

    The adapter wraps the existing governance policy update and rollback paths,
    preserving four-eyes approval and policy history semantics while exposing
    deterministic bind-boundary snapshots.
    """

    policy_reader: Callable[[], dict[str, Any]]
    policy_updater: Callable[[dict[str, Any]], dict[str, Any]]
    policy_patch: dict[str, Any]
    policy_rollback: Callable[..., dict[str, Any]] | None = None
    revert_actor: str = "bind_boundary"
    approval_records: list[dict[str, Any]] | None = None
    target_description: str = "governance/policy"

    def __post_init__(self) -> None:
        self._last_updated_policy: dict[str, Any] | None = None
        self._effective_patch = _governance_effective_patch(self.policy_patch)

    def snapshot(self) -> dict[str, Any]:
        """Capture deterministic policy snapshot."""
        return {"policy": self.policy_reader()}

    def fingerprint_state(self, snapshot: Any) -> str:
        """Return deterministic fingerprint for policy snapshot."""
        if not isinstance(snapshot, dict):
            raise ValueError("BIND_STATE_SNAPSHOT_INVALID")
        policy = snapshot.get("policy")
        if not isinstance(policy, dict):
            raise ValueError("BIND_POLICY_SNAPSHOT_INVALID")
        return sha256_of_canonical_json(policy)

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Require explicit authority flag in bind approval context."""
        del snapshot
        if not isinstance(intent.approval_context, dict):
            return False
        return bool(intent.approval_context.get("governance_policy_update_approved"))

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        """Validate deterministic local constraints for policy patch."""
        del intent
        policy = snapshot.get("policy") if isinstance(snapshot, dict) else None
        return {
            "patch_is_dict": isinstance(self._effective_patch, dict),
            "snapshot_has_policy": isinstance(policy, dict),
        }

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Assess runtime risk for in-process governed policy update."""
        del intent, snapshot
        return True

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Apply governed policy patch via existing update path."""
        del intent, snapshot
        updated = self.policy_updater(self.policy_patch)
        if not isinstance(updated, dict):
            raise ValueError("BIND_POLICY_UPDATE_INVALID")
        self._last_updated_policy = updated
        return True

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Verify that patched fields are reflected in the persisted policy."""
        del intent
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("policy"), dict):
            return False

        latest = self._last_updated_policy if isinstance(self._last_updated_policy, dict) else self.policy_reader()
        if not isinstance(latest, dict):
            return False
        return _dict_contains_patch(latest, self._effective_patch)

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Revert failed apply by restoring pre-apply policy snapshot."""
        del intent
        if not isinstance(snapshot, dict):
            return False
        previous_policy = snapshot.get("policy")
        if not isinstance(previous_policy, dict):
            return False

        if callable(self.policy_rollback):
            self.policy_rollback(
                previous_policy,
                rolled_back_by=self.revert_actor,
                approvals=self.approval_records,
                reason="bind_postcondition_failure_revert",
            )
            return True

        self.policy_updater(previous_policy)
        return True

    def describe_target(self) -> str:
        """Return human-readable target descriptor."""
        return self.target_description


def _dict_contains_patch(target: dict[str, Any], patch: dict[str, Any]) -> bool:
    """Return True when ``target`` recursively includes all ``patch`` values."""
    for key, expected in patch.items():
        if key not in target:
            return False
        actual = target[key]
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            if not _dict_contains_patch(actual, expected):
                return False
            continue
        if actual != expected:
            return False
    return True


def _governance_effective_patch(policy_patch: dict[str, Any]) -> dict[str, Any]:
    """Filter transient governance request metadata from postcondition checks."""
    ignored_fields = {
        "approvals",
        "approval",
        "_event_type",
        "policy_lineage",
        "execution_intent_id",
        "bind_receipt_id",
        "decision_id",
        "request_id",
    }
    return {key: value for key, value in policy_patch.items() if key not in ignored_fields}


@dataclass
class PolicyBundlePromotionAdapter(BindAdapterContract):
    """Bind adapter for active policy-bundle pointer promotion.

    The adapter promotes a single pointer file that identifies the active
    compiled policy bundle directory used by operational code paths.
    """

    pointer_path: Path
    allowed_root: Path
    require_signature: bool = False
    target_description: str = "governance/policy_bundle_promotion"

    def snapshot(self) -> dict[str, Any]:
        """Return deterministic snapshot of current pointer state."""
        if not self.pointer_path.exists():
            return {
                "pointer_exists": False,
                "active_bundle_dir": "",
                "decision_id": "",
                "execution_intent_id": "",
            }

        payload = self._read_pointer_payload(self.pointer_path)
        return {
            "pointer_exists": True,
            "active_bundle_dir": str(payload.get("active_bundle_dir") or ""),
            "decision_id": str(payload.get("decision_id") or ""),
            "execution_intent_id": str(payload.get("execution_intent_id") or ""),
        }

    def fingerprint_state(self, snapshot: Any) -> str:
        """Return deterministic state fingerprint for snapshot payload."""
        if not isinstance(snapshot, dict):
            raise ValueError("BIND_STATE_SNAPSHOT_INVALID")
        return sha256_of_canonical_json(snapshot)

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Require explicit promotion approval in execution intent context."""
        del snapshot
        if not isinstance(intent.approval_context, dict):
            return False
        return bool(intent.approval_context.get("policy_bundle_promotion_approved"))

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        """Validate deterministic local constraints for promotion target."""
        del snapshot
        target_dir = self._resolve_target(intent)
        return {
            "target_within_allowed_root": self._is_within_allowed_root(target_dir),
            "manifest_exists": (target_dir / "manifest.json").exists(),
            "canonical_ir_exists": (target_dir / "compiled" / "canonical_ir.json").exists(),
        }

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        """Assess runtime risk by checking pointer write safety conditions."""
        del snapshot
        target_dir = self._resolve_target(intent)
        return self._is_within_allowed_root(target_dir)

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Apply promotion by atomically writing active bundle pointer."""
        del snapshot
        target_dir = self._resolve_target(intent)
        pointer_payload = {
            "active_bundle_dir": str(target_dir),
            "decision_id": intent.decision_id,
            "execution_intent_id": intent.execution_intent_id,
        }
        self.pointer_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.pointer_path, pointer_payload, indent=2)
        return True

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Verify pointer now references a valid target bundle directory."""
        del snapshot
        target_dir = self._resolve_target(intent)
        payload = self._read_pointer_payload(self.pointer_path)
        points_to_target = str(payload.get("active_bundle_dir") or "") == str(target_dir)
        if not points_to_target:
            return False

        if not (target_dir / "manifest.json").exists():
            return False
        if not (target_dir / "compiled" / "canonical_ir.json").exists():
            return False

        if self.require_signature and not (target_dir / "manifest.sig").exists():
            return False
        return True

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        """Revert promotion by restoring pre-apply pointer snapshot."""
        del intent
        if not isinstance(snapshot, dict):
            return False

        pointer_exists = bool(snapshot.get("pointer_exists"))
        if not pointer_exists:
            self.pointer_path.unlink(missing_ok=True)
            return True

        restored_payload = {
            "active_bundle_dir": str(snapshot.get("active_bundle_dir") or ""),
            "decision_id": str(snapshot.get("decision_id") or ""),
            "execution_intent_id": str(snapshot.get("execution_intent_id") or ""),
        }
        self.pointer_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.pointer_path, restored_payload, indent=2)
        return True

    def describe_target(self) -> str:
        """Return human-readable target descriptor."""
        return self.target_description

    def _resolve_target(self, intent: ExecutionIntent) -> Path:
        target = Path(intent.target_resource).expanduser().resolve()
        return target

    def _is_within_allowed_root(self, target_dir: Path) -> bool:
        try:
            target_dir.relative_to(self.allowed_root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _read_pointer_payload(path: Path) -> dict[str, Any]:
        import json

        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("BIND_POINTER_PAYLOAD_INVALID")
        return loaded
