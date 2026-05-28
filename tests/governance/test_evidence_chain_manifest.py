"""Tests for deterministic local/offline Evidence Chain Manifest v1."""

from __future__ import annotations

from veritas_os.governance.evidence_chain_manifest import (
    EvidenceChainManifest,
    build_evidence_chain_manifest,
    validate_evidence_chain_manifest,
    with_manifest_hash,
)


def _base_manifest() -> EvidenceChainManifest:
    return EvidenceChainManifest(
        manifest_id="ecm-op-1",
        decision_id="decision-1",
        execution_intent_id="intent-1",
        operation_id="operation-1",
        action_class="permission_change",
        target_system="mock_saas",
        target_resource="user:alice",
        requested_scope=["saas:grant_admin"],
        authority_evidence_id="aev-1",
        authority_evidence_hash="a" * 64,
        human_approval_receipt_id="har-1",
        human_approval_receipt_hash="b" * 64,
        bind_receipt_id=None,
        bind_receipt_hash=None,
        outcome_receipt_id="outcome-1",
        outcome_receipt_hash="c" * 64,
        bind_coverage_operation_id="saas_permission_change_demo",
        final_outcome="commit",
        chain_status="complete",
        missing_links=[],
        refusal_basis=[],
        observed_effects_summary=[{"effect_type": "permission_grant"}],
        generated_at="2026-04-26T00:00:00+00:00",
        manifest_hash="",
        metadata={"fixture_only": True},
    )


def test_valid_complete_manifest_has_deterministic_non_empty_manifest_hash() -> None:
    manifest = with_manifest_hash(_base_manifest())
    assert manifest.manifest_hash
    assert validate_evidence_chain_manifest(manifest).is_valid is True


def test_same_content_produces_same_manifest_hash() -> None:
    assert with_manifest_hash(_base_manifest()).manifest_hash == with_manifest_hash(_base_manifest()).manifest_hash


def test_changing_meaningful_field_changes_manifest_hash() -> None:
    one = with_manifest_hash(_base_manifest())
    changed = _base_manifest()
    changed_data = changed.to_dict()
    changed_data["target_resource"] = "user:bob"
    two = with_manifest_hash(EvidenceChainManifest(**changed_data))
    assert one.manifest_hash != two.manifest_hash


def test_manifest_hash_does_not_recursively_affect_its_own_hash() -> None:
    manifest = with_manifest_hash(_base_manifest())
    mutated = EvidenceChainManifest(**{**manifest.to_dict(), "manifest_hash": "x" * 64})
    assert manifest.deterministic_digest() == mutated.deterministic_digest()


def test_missing_manifest_fails_validation() -> None:
    result = validate_evidence_chain_manifest(None)
    assert result.is_valid is False
    assert "evidence_chain_manifest_missing" in result.failure_reasons


def test_invalid_chain_status_fails_validation() -> None:
    manifest = with_manifest_hash(EvidenceChainManifest(**{**_base_manifest().to_dict(), "chain_status": "bad"}))
    result = validate_evidence_chain_manifest(manifest)
    assert result.is_valid is False
    assert "evidence_chain_invalid_chain_status" in result.failure_reasons


def test_complete_manifest_missing_required_hashes_fails_validation() -> None:
    manifest = with_manifest_hash(
        EvidenceChainManifest(**{**_base_manifest().to_dict(), "authority_evidence_hash": None})
    )
    result = validate_evidence_chain_manifest(manifest)
    assert "evidence_chain_complete_missing_required_hash" in result.failure_reasons


def test_complete_manifest_with_missing_links_fails_validation() -> None:
    manifest = with_manifest_hash(
        EvidenceChainManifest(**{**_base_manifest().to_dict(), "missing_links": ["authority_evidence_hash"]})
    )
    result = validate_evidence_chain_manifest(manifest)
    assert "evidence_chain_complete_has_missing_links" in result.failure_reasons


def test_blocked_manifest_with_commit_outcome_fails_validation() -> None:
    manifest = with_manifest_hash(
        EvidenceChainManifest(
            **{**_base_manifest().to_dict(), "chain_status": "blocked", "final_outcome": "commit", "refusal_basis": ["x"]}
        )
    )
    result = validate_evidence_chain_manifest(manifest)
    assert "evidence_chain_blocked_outcome_mismatch" in result.failure_reasons


def test_blocked_manifest_without_refusal_basis_fails_validation() -> None:
    manifest = with_manifest_hash(
        EvidenceChainManifest(**{**_base_manifest().to_dict(), "chain_status": "blocked", "final_outcome": "block", "refusal_basis": []})
    )
    result = validate_evidence_chain_manifest(manifest)
    assert "evidence_chain_blocked_without_refusal_basis" in result.failure_reasons


def test_generated_at_unparseable_fails_validation() -> None:
    manifest = with_manifest_hash(EvidenceChainManifest(**{**_base_manifest().to_dict(), "generated_at": "bad"}))
    result = validate_evidence_chain_manifest(manifest)
    assert "evidence_chain_generated_at_unparseable" in result.failure_reasons


def test_build_evidence_chain_manifest_returns_hash_populated_manifest() -> None:
    manifest = build_evidence_chain_manifest(
        decision_id="decision-1",
        execution_intent_id="intent-1",
        operation_id="op-1",
        action_class="permission_change",
        target_system="mock_saas",
        target_resource="user:alice",
        requested_scope=["saas:grant_admin"],
        final_outcome="commit",
        authority_evidence_hash="a" * 64,
        human_approval_receipt_hash="b" * 64,
        outcome_receipt_hash="c" * 64,
        bind_coverage_operation_id="saas_permission_change_demo",
        generated_at="2026-04-26T00:00:00+00:00",
    )
    assert manifest.manifest_hash


def test_build_evidence_chain_manifest_derives_complete_when_required_links_exist() -> None:
    manifest = build_evidence_chain_manifest(
        decision_id="d",
        execution_intent_id="i",
        operation_id="op",
        action_class="ac",
        target_system="ts",
        target_resource="tr",
        requested_scope=["x"],
        final_outcome="commit",
        authority_evidence_hash="a" * 64,
        human_approval_receipt_hash="b" * 64,
        outcome_receipt_hash="c" * 64,
        bind_coverage_operation_id="cov",
        generated_at="2026-04-26T00:00:00+00:00",
    )
    assert manifest.chain_status == "complete"


def test_build_evidence_chain_manifest_derives_blocked_when_final_outcome_blocked() -> None:
    manifest = build_evidence_chain_manifest(
        decision_id="d",
        execution_intent_id="i",
        operation_id="op",
        action_class="ac",
        target_system="ts",
        target_resource="tr",
        requested_scope=["x"],
        final_outcome="blocked",
        refusal_basis=["authority_missing"],
        generated_at="2026-04-26T00:00:00+00:00",
    )
    assert manifest.chain_status == "blocked"


def test_build_evidence_chain_manifest_derives_incomplete_when_non_blocked_lacks_links() -> None:
    manifest = build_evidence_chain_manifest(
        decision_id="d",
        execution_intent_id="i",
        operation_id="op",
        action_class="ac",
        target_system="ts",
        target_resource="tr",
        requested_scope=["x"],
        final_outcome="commit",
        generated_at="2026-04-26T00:00:00+00:00",
    )
    assert manifest.chain_status == "incomplete"
