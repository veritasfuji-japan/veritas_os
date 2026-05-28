"""Deterministic local/offline bind coverage registry for effect-bearing operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EffectLevel = Literal["low", "medium", "high", "critical"]
OperationType = Literal["route", "script", "governance_action", "demo"]
AuthorityControlType = Literal["authority_evidence", "bind_authority_signal", "none"]
BlockBehavior = Literal["block", "not_required"]
FailureMode = Literal["fail_closed"]

_ALLOWED_EFFECT_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class BindCoverageEntry:
    """Registry row describing bind-governance expectations for one operation."""

    operation_id: str
    operation_type: OperationType
    action_class: str
    effect_level: EffectLevel
    requires_bind: bool
    authority_control_type: AuthorityControlType
    requires_authority_evidence: bool
    requires_human_approval: bool
    requires_policy_snapshot: bool
    expected_without_authority: BlockBehavior
    expected_without_human_approval: BlockBehavior
    default_failure_mode: FailureMode
    implementation_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    docs_refs: tuple[str, ...]
    boundary_note: str


@dataclass(frozen=True)
class BindCoverageValidationResult:
    """Validation output for the deterministic bind coverage registry."""

    valid: bool
    errors: tuple[str, ...]


_BIND_COVERAGE_REGISTRY: tuple[BindCoverageEntry, ...] = (
    BindCoverageEntry(
        operation_id="saas_permission_change_demo",
        operation_type="demo",
        action_class="permission_change",
        effect_level="high",
        requires_bind=True,
        authority_control_type="authority_evidence",
        requires_authority_evidence=True,
        requires_human_approval=True,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="block",
        default_failure_mode="fail_closed",
        implementation_refs=(
            "scripts/demo/saas_permission_change_governed_demo.py",
            "veritas_os/governance/commit_boundary.py",
            "veritas_os/governance/runtime_authority.py",
        ),
        test_refs=("tests/demo/test_saas_permission_change_governed_demo.py",),
        docs_refs=("docs/en/demo/saas-permission-change-governed-demo.md",),
        boundary_note="local/offline fixture only; no live SaaS/IAM/IdP integration",
    ),
    BindCoverageEntry(
        operation_id="aml_kyc_regulated_action_path",
        operation_type="governance_action",
        action_class="aml_kyc_customer_risk_escalation",
        effect_level="critical",
        requires_bind=True,
        authority_control_type="authority_evidence",
        requires_authority_evidence=True,
        requires_human_approval=True,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="block",
        default_failure_mode="fail_closed",
        implementation_refs=(
            "veritas_os/governance/regulated_action_path.py",
            "veritas_os/governance/commit_boundary.py",
            "veritas_os/governance/runtime_authority.py",
        ),
        test_refs=("tests/governance/test_aml_kyc_regulated_action_path.py",),
        docs_refs=("docs/en/architecture/regulated-action-governance-kernel.md",),
        boundary_note="deterministic local/offline AML-KYC fixture; no live bank/sanctions systems",
    ),
    BindCoverageEntry(
        operation_id="governance_policy_update_put",
        operation_type="route",
        action_class="governance_policy_update",
        effect_level="high",
        requires_bind=True,
        authority_control_type="bind_authority_signal",
        requires_authority_evidence=False,
        requires_human_approval=True,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="block",
        default_failure_mode="fail_closed",
        implementation_refs=(
            "veritas_os/api/routes_governance.py",
            "veritas_os/policy/governance_policy_update.py",
            "veritas_os/policy/bind_execution.py",
        ),
        test_refs=(
            "tests/test_bind_admissibility.py",
            "tests/governance/test_commit_boundary.py",
        ),
        docs_refs=("docs/en/architecture/bind-boundary-governance-artifacts.md",),
        boundary_note="bind-governed policy mutation path with deterministic local validation",
    ),
)


def load_bind_coverage_registry() -> list[BindCoverageEntry]:
    """Return the deterministic bind coverage registry entries."""

    return list(_BIND_COVERAGE_REGISTRY)


def validate_bind_coverage_registry(
    entries: list[BindCoverageEntry],
) -> BindCoverageValidationResult:
    """Validate entry integrity and fail-closed governance expectations."""

    errors: list[str] = []
    seen_ids: set[str] = set()

    for entry in entries:
        if not entry.operation_id.strip():
            errors.append("operation_id must be non-empty")
        elif entry.operation_id in seen_ids:
            errors.append(f"duplicate operation_id: {entry.operation_id}")
        seen_ids.add(entry.operation_id)

        if entry.effect_level not in _ALLOWED_EFFECT_LEVELS:
            errors.append(
                f"invalid effect_level for {entry.operation_id}: {entry.effect_level}"
            )
        if entry.authority_control_type not in {
            "authority_evidence",
            "bind_authority_signal",
            "none",
        }:
            errors.append(
                "invalid authority_control_type for "
                f"{entry.operation_id}: {entry.authority_control_type}"
            )

        if entry.effect_level in {"high", "critical"} and not entry.requires_bind:
            errors.append(
                f"high/critical operation must require bind: {entry.operation_id}"
            )

        if (
            entry.effect_level in {"high", "critical"}
            and entry.default_failure_mode != "fail_closed"
        ):
            errors.append(
                f"high/critical operation must fail closed: {entry.operation_id}"
            )

        if entry.authority_control_type == "authority_evidence":
            if not entry.requires_authority_evidence:
                errors.append(
                    "authority_evidence control must require authority evidence: "
                    f"{entry.operation_id}"
                )
            if entry.expected_without_authority != "block":
                errors.append(
                    "authority_evidence control must block without authority: "
                    f"{entry.operation_id}"
                )

        if (
            entry.requires_authority_evidence
            and entry.authority_control_type != "authority_evidence"
        ):
            errors.append(
                "requires_authority_evidence=true requires authority_control_type "
                f"authority_evidence: {entry.operation_id}"
            )

        if (
            entry.authority_control_type == "bind_authority_signal"
            and entry.expected_without_authority != "block"
        ):
            errors.append(
                "bind_authority_signal operation must block without authority: "
                f"{entry.operation_id}"
            )

        if (
            entry.requires_human_approval
            and entry.expected_without_human_approval != "block"
        ):
            errors.append(
                "human-approval-required operation must block without approval: "
                f"{entry.operation_id}"
            )

        if not entry.implementation_refs:
            errors.append(
                f"implementation_refs must be non-empty: {entry.operation_id}"
            )

        if not entry.docs_refs:
            errors.append(f"docs_refs should be non-empty: {entry.operation_id}")

        note = entry.boundary_note.lower()
        if "live" in note and "no live" not in note:
            errors.append(
                f"entry may not claim live integration: {entry.operation_id}"
            )

    return BindCoverageValidationResult(valid=not errors, errors=tuple(errors))
