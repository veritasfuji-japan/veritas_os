"""Deterministic local/offline bind coverage registry for effect-bearing operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from veritas_os.policy.bind_execution_capability import PROOF_SCOPE

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
    coverage_entry_id: str = ""
    authorization_mode: str = ""
    execution_entrypoint_id: str = ""
    runtime_implementation: str = ""
    effect_boundary_id: str = ""
    dispatch_kind: str = ""
    endpoint_binding_requirements: tuple[str, ...] = ()
    credential_binding_requirements: tuple[str, ...] = ()
    request_binding_requirements: tuple[str, ...] = ()
    proof_scope: str = ""


@dataclass(frozen=True)
class BindCoverageValidationResult:
    """Validation output for the deterministic bind coverage registry."""

    valid: bool
    errors: tuple[str, ...]


_BIND_COVERAGE_REGISTRY: tuple[BindCoverageEntry, ...] = (
    BindCoverageEntry(
        operation_id="registered_webhook_action",
        operation_type="governance_action",
        action_class="registered_webhook",
        effect_level="critical",
        requires_bind=True,
        authority_control_type="authority_evidence",
        requires_authority_evidence=True,
        requires_human_approval=True,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="block",
        default_failure_mode="fail_closed",
        implementation_refs=("veritas_os/policy/webhook_bind_adapter.py",),
        test_refs=("tests/policy/test_bind_coverage_bypass_resistance_v1.py",),
        docs_refs=("docs/en/architecture/bind-coverage-bypass-resistance-v1.md",),
        boundary_note="registered webhook ACTION only",
        coverage_entry_id="bcb-v1-registered-webhook-action",
        authorization_mode="consumed_live_adapter_bind_authorization",
        execution_entrypoint_id="webhook-bind-adapter.apply",
        runtime_implementation="veritas_os.policy.webhook_bind_adapter.WebhookBindAdapter",
        effect_boundary_id="registered-webhook-action",
        dispatch_kind="ACTION",
        endpoint_binding_requirements=("canonical_https_endpoint",),
        credential_binding_requirements=("credential_reference", "credential_scope"),
        request_binding_requirements=("canonical_body_bytes", "idempotency_identity"),
        proof_scope=PROOF_SCOPE,
    ),
    BindCoverageEntry(
        operation_id="registered_webhook_compensation",
        operation_type="governance_action",
        action_class="registered_webhook",
        effect_level="critical",
        requires_bind=True,
        authority_control_type="authority_evidence",
        requires_authority_evidence=True,
        requires_human_approval=True,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="block",
        default_failure_mode="fail_closed",
        implementation_refs=("veritas_os/policy/webhook_bind_adapter.py",),
        test_refs=("tests/policy/test_bind_coverage_bypass_resistance_v1.py",),
        docs_refs=("docs/en/architecture/bind-coverage-bypass-resistance-v1.md",),
        boundary_note="registered webhook COMPENSATION only",
        coverage_entry_id="bcb-v1-registered-webhook-compensation",
        authorization_mode="bind_core_compensation_grant",
        execution_entrypoint_id="webhook-bind-adapter.revert",
        runtime_implementation="veritas_os.policy.webhook_bind_adapter.WebhookBindAdapter",
        effect_boundary_id="registered-webhook-compensation",
        dispatch_kind="COMPENSATION",
        endpoint_binding_requirements=("canonical_https_endpoint",),
        credential_binding_requirements=("credential_reference", "credential_scope"),
        request_binding_requirements=("canonical_body_bytes", "parent_action"),
        proof_scope=PROOF_SCOPE,
    ),
    BindCoverageEntry(
        operation_id="native_v2_sandbox_action",
        operation_type="governance_action",
        action_class="sandbox.event.register.v1",
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
            "veritas_os/policy/sandbox_bind_execution.py",
            "veritas_os/policy/sandbox_https_transport.py",
        ),
        test_refs=("tests/policy/test_bind_coverage_bypass_resistance_v1.py",),
        docs_refs=("docs/en/architecture/bind-coverage-bypass-resistance-v1.md",),
        boundary_note="native-v2 sandbox ACTION only",
        coverage_entry_id="bcb-v1-native-v2-sandbox-action",
        authorization_mode="consumed_native_v2_authorization",
        execution_entrypoint_id="sandbox-https-transport.send-once",
        runtime_implementation="veritas_os.policy.sandbox_https_transport.SandboxHTTPSTransport",
        effect_boundary_id="native-v2-sandbox-action",
        dispatch_kind="ACTION",
        endpoint_binding_requirements=("exact_deployment_endpoint",),
        credential_binding_requirements=("credential_reference", "credential_scope"),
        request_binding_requirements=("exact_body_bytes", "idempotency_identity"),
        proof_scope=PROOF_SCOPE,
    ),
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
    seen_coverage_ids: set[str] = set()
    seen_boundaries: set[tuple[str, str, str]] = set()

    for entry in entries:
        if not entry.operation_id.strip():
            errors.append("operation_id must be non-empty")
        elif entry.operation_id in seen_ids:
            errors.append(f"duplicate operation_id: {entry.operation_id}")
        seen_ids.add(entry.operation_id)

        if entry.proof_scope == PROOF_SCOPE:
            if not entry.coverage_entry_id or entry.coverage_entry_id in seen_coverage_ids:
                errors.append(
                    f"duplicate or empty coverage_entry_id: {entry.coverage_entry_id}"
                )
            seen_coverage_ids.add(entry.coverage_entry_id)
            boundary = (
                entry.runtime_implementation,
                entry.effect_boundary_id,
                entry.dispatch_kind,
            )
            if not all(boundary) or boundary in seen_boundaries:
                errors.append(f"duplicate or incomplete exact boundary: {boundary}")
            seen_boundaries.add(boundary)
            if not (
                entry.execution_entrypoint_id
                and entry.authorization_mode
                and entry.endpoint_binding_requirements
                and entry.credential_binding_requirements
                and entry.request_binding_requirements
            ):
                errors.append(
                    f"incomplete executable coverage entry: {entry.coverage_entry_id}"
                )

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


def match_frozen_runtime_boundary(
    runtime: object,
    *,
    effect_boundary_id: str,
    dispatch_kind: str,
    entries: list[BindCoverageEntry] | None = None,
) -> BindCoverageEntry:
    """Return exactly one exact-class V1 match or fail closed."""
    identity = f"{type(runtime).__module__}.{type(runtime).__qualname__}"
    matches = [
        entry
        for entry in (entries or load_bind_coverage_registry())
        if entry.proof_scope == PROOF_SCOPE
        and entry.runtime_implementation == identity
        and entry.effect_boundary_id == effect_boundary_id
        and entry.dispatch_kind == dispatch_kind
    ]
    if len(matches) != 1:
        raise ValueError("BIND_COVERAGE_EXACT_RUNTIME_MATCH_REQUIRED")
    return matches[0]
