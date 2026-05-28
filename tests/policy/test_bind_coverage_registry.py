"""Tests for deterministic bind coverage registry v1."""

from __future__ import annotations

from veritas_os.policy.bind_coverage_registry import (
    BindCoverageEntry,
    load_bind_coverage_registry,
    validate_bind_coverage_registry,
)


def _entry(entries: list[BindCoverageEntry], operation_id: str) -> BindCoverageEntry:
    for item in entries:
        if item.operation_id == operation_id:
            return item
    raise AssertionError(f"missing operation_id: {operation_id}")


def test_registry_loads_successfully() -> None:
    entries = load_bind_coverage_registry()
    result = validate_bind_coverage_registry(entries)
    assert entries
    assert result.valid is True


def test_operation_ids_are_unique() -> None:
    entries = load_bind_coverage_registry()
    operation_ids = [entry.operation_id for entry in entries]
    assert len(operation_ids) == len(set(operation_ids))


def test_high_critical_entries_require_bind() -> None:
    entries = load_bind_coverage_registry()
    for entry in entries:
        if entry.effect_level in {"high", "critical"}:
            assert entry.requires_bind is True


def test_high_critical_entries_fail_closed() -> None:
    entries = load_bind_coverage_registry()
    for entry in entries:
        if entry.effect_level in {"high", "critical"}:
            assert entry.default_failure_mode == "fail_closed"


def test_authority_required_entries_block_without_authority() -> None:
    entries = load_bind_coverage_registry()
    for entry in entries:
        if entry.requires_authority_evidence:
            assert entry.expected_without_authority == "block"


def test_human_approval_required_entries_block_without_human_approval() -> None:
    entries = load_bind_coverage_registry()
    for entry in entries:
        if entry.requires_human_approval:
            assert entry.expected_without_human_approval == "block"


def test_saas_permission_change_demo_entry_exists() -> None:
    entries = load_bind_coverage_registry()
    assert _entry(entries, "saas_permission_change_demo")


def test_saas_permission_change_demo_requires_authority_evidence() -> None:
    entry = _entry(load_bind_coverage_registry(), "saas_permission_change_demo")
    assert entry.requires_authority_evidence is True
    assert entry.authority_control_type == "authority_evidence"


def test_aml_kyc_path_uses_authority_evidence_control() -> None:
    entry = _entry(load_bind_coverage_registry(), "aml_kyc_regulated_action_path")
    assert entry.authority_control_type == "authority_evidence"
    assert entry.requires_authority_evidence is True


def test_saas_permission_change_demo_requires_human_approval() -> None:
    entry = _entry(load_bind_coverage_registry(), "saas_permission_change_demo")
    assert entry.requires_human_approval is True


def test_governance_policy_update_uses_bind_authority_signal() -> None:
    entry = _entry(load_bind_coverage_registry(), "governance_policy_update_put")
    assert entry.authority_control_type == "bind_authority_signal"
    assert entry.requires_authority_evidence is False
    assert entry.expected_without_authority == "block"


def test_validator_fails_for_duplicate_operation_id() -> None:
    entries = load_bind_coverage_registry()
    duplicate = entries[0]
    result = validate_bind_coverage_registry(entries + [duplicate])
    assert result.valid is False
    assert any("duplicate operation_id" in error for error in result.errors)


def test_validator_fails_for_high_effect_without_bind() -> None:
    invalid_entry = BindCoverageEntry(
        operation_id="invalid_high_without_bind",
        operation_type="demo",
        action_class="permission_change",
        effect_level="high",
        requires_bind=False,
        authority_control_type="none",
        requires_authority_evidence=False,
        requires_human_approval=False,
        requires_policy_snapshot=True,
        expected_without_authority="not_required",
        expected_without_human_approval="not_required",
        default_failure_mode="fail_closed",
        implementation_refs=("scripts/demo/saas_permission_change_governed_demo.py",),
        test_refs=("tests/demo/test_saas_permission_change_governed_demo.py",),
        docs_refs=("docs/en/demo/saas-permission-change-governed-demo.md",),
        boundary_note="local/offline deterministic fixture",
    )
    result = validate_bind_coverage_registry([invalid_entry])
    assert result.valid is False
    assert any("must require bind" in error for error in result.errors)


def test_validator_fails_for_authority_required_without_block() -> None:
    invalid_entry = BindCoverageEntry(
        operation_id="invalid_authority_expectation",
        operation_type="script",
        action_class="regulated_action",
        effect_level="medium",
        requires_bind=True,
        authority_control_type="authority_evidence",
        requires_authority_evidence=True,
        requires_human_approval=False,
        requires_policy_snapshot=True,
        expected_without_authority="not_required",
        expected_without_human_approval="not_required",
        default_failure_mode="fail_closed",
        implementation_refs=("veritas_os/governance/regulated_action_path.py",),
        test_refs=("tests/governance/test_aml_kyc_regulated_action_path.py",),
        docs_refs=("docs/en/architecture/regulated-action-governance-kernel.md",),
        boundary_note="local/offline deterministic fixture",
    )
    result = validate_bind_coverage_registry([invalid_entry])
    assert result.valid is False
    assert any("must block without authority" in error for error in result.errors)


def test_validator_fails_when_requires_authority_but_control_type_is_not_evidence() -> None:
    invalid_entry = BindCoverageEntry(
        operation_id="invalid_authority_control_pairing",
        operation_type="script",
        action_class="regulated_action",
        effect_level="medium",
        requires_bind=True,
        authority_control_type="bind_authority_signal",
        requires_authority_evidence=True,
        requires_human_approval=False,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="not_required",
        default_failure_mode="fail_closed",
        implementation_refs=("veritas_os/governance/regulated_action_path.py",),
        test_refs=("tests/governance/test_aml_kyc_regulated_action_path.py",),
        docs_refs=("docs/en/architecture/regulated-action-governance-kernel.md",),
        boundary_note="local/offline deterministic fixture",
    )
    result = validate_bind_coverage_registry([invalid_entry])
    assert result.valid is False
    assert any("requires_authority_evidence=true" in error for error in result.errors)


def test_validator_fails_when_authority_evidence_control_has_no_evidence_requirement() -> None:
    invalid_entry = BindCoverageEntry(
        operation_id="invalid_authority_evidence_missing_requirement",
        operation_type="demo",
        action_class="permission_change",
        effect_level="high",
        requires_bind=True,
        authority_control_type="authority_evidence",
        requires_authority_evidence=False,
        requires_human_approval=False,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="not_required",
        default_failure_mode="fail_closed",
        implementation_refs=("scripts/demo/saas_permission_change_governed_demo.py",),
        test_refs=("tests/demo/test_saas_permission_change_governed_demo.py",),
        docs_refs=("docs/en/demo/saas-permission-change-governed-demo.md",),
        boundary_note="local/offline deterministic fixture",
    )
    result = validate_bind_coverage_registry([invalid_entry])
    assert result.valid is False
    assert any("must require authority evidence" in error for error in result.errors)


def test_validator_fails_for_invalid_authority_control_type() -> None:
    invalid_entry = BindCoverageEntry(
        operation_id="invalid_authority_control_type",
        operation_type="route",
        action_class="governance_policy_update",
        effect_level="medium",
        requires_bind=True,
        authority_control_type="invalid",  # type: ignore[arg-type]
        requires_authority_evidence=False,
        requires_human_approval=True,
        requires_policy_snapshot=True,
        expected_without_authority="block",
        expected_without_human_approval="block",
        default_failure_mode="fail_closed",
        implementation_refs=("veritas_os/policy/governance_policy_update.py",),
        test_refs=("tests/governance/test_commit_boundary.py",),
        docs_refs=("docs/en/architecture/bind-boundary-governance-artifacts.md",),
        boundary_note="local/offline deterministic fixture",
    )
    result = validate_bind_coverage_registry([invalid_entry])
    assert result.valid is False
    assert any("invalid authority_control_type" in error for error in result.errors)


def test_validator_allows_bind_authority_signal_without_authority_evidence() -> None:
    valid_entry = BindCoverageEntry(
        operation_id="valid_bind_authority_signal_entry",
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
        implementation_refs=("veritas_os/policy/governance_policy_update.py",),
        test_refs=("tests/governance/test_commit_boundary.py",),
        docs_refs=("docs/en/architecture/bind-boundary-governance-artifacts.md",),
        boundary_note="local/offline deterministic fixture",
    )
    result = validate_bind_coverage_registry([valid_entry])
    assert result.valid is True
