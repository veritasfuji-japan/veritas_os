"""Regression guards for the controlled Execution Proof architecture freeze."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    ReconciliationClaim,
)
from veritas_os.policy.native_bind_authorization import NativeBindAuthorizationArtifact
from veritas_os.policy.sandbox_bind_execution import (
    REQUEST_TIMEOUT_SECONDS,
    SandboxDispatchRequest,
)
from veritas_os.policy.sandbox_recovery import SandboxRecoveryResult

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT / "docs" / "architecture" / "controlled-execution-proof-freeze-v1.json"
)
ANCHOR = "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_architecture_freeze_manifest_is_pinned_to_proven_anchor() -> None:
    manifest = _manifest()
    assert manifest["format_version"] == (
        "controlled-execution-proof-architecture-freeze/v1"
    )
    assert manifest["status"] == "FROZEN_CONTROLLED_PROOF_SCOPE"
    assert manifest["freeze_anchor_commit"] == ANCHOR
    assert manifest["proof_pr"] == 2215
    assert manifest["required_check"] == "reproducible-decision-to-effect-e2e"
    assert manifest["proof_scope"] == (
        "controlled-current-head-decision-to-effect-sandbox"
    )
    assert manifest["external_effect_scope"] == (
        "synthetic-sandbox-event-persistence"
    )


def test_architecture_freeze_required_files_remain_present() -> None:
    manifest = _manifest()
    for relative in manifest["required_files"]:
        assert (ROOT / relative).is_file(), relative


def test_architecture_freeze_invariants_and_non_claims_are_explicit() -> None:
    manifest = _manifest()
    assert set(manifest["frozen_invariants"]) == {
        "authorization_issuance_is_not_execution_permission",
        "single_use_consumption_is_required",
        "current_governance_rechecks_precede_effect",
        "dispatch_intent_is_durable_before_transport",
        "effect_unknown_is_not_failure",
        "lookup_absence_is_not_no_effect",
        "blind_redispatch_is_prohibited",
        "replacement_business_event_is_blocked_while_unresolved_or_confirmed",
        "reconciliation_is_read_only",
        "receipt_outcome_are_retrospective_evidence_not_authority",
        "recovery_never_resends_external_effect",
        "decision_authorization_receipt_lineage_is_preserved",
    }
    assert set(manifest["explicit_non_claims"]) == {
        "production_readiness",
        "real_customer_credentials",
        "real_customer_endpoint",
        "independent_production_infrastructure",
        "external_utc_clock_trust",
        "trustlog_exactly_once_publication",
        "regulatory_approval_or_certification",
    }


def test_frozen_runtime_types_preserve_single_use_unknown_and_no_retry_semantics() -> None:
    assert get_args(
        NativeBindAuthorizationArtifact.model_fields["single_use"].annotation
    ) == (True,)
    assert get_args(
        NativeBindAuthorizationArtifact.model_fields[
            "authorization_consumption_required"
        ].annotation
    ) == (True,)
    assert get_args(
        NativeBindAuthorizationArtifact.model_fields[
            "duplicate_dispatch_prohibited"
        ].annotation
    ) == (True,)
    assert set(EffectExecutionState) == {
        EffectExecutionState.IN_FLIGHT,
        EffectExecutionState.EFFECT_UNKNOWN,
        EffectExecutionState.CONFIRMED_EFFECT,
        EffectExecutionState.CONFIRMED_NO_EFFECT,
    }
    assert set(ReconciliationClaim) == {
        ReconciliationClaim.CONFIRMED_EFFECT,
        ReconciliationClaim.CONFIRMED_NO_EFFECT,
        ReconciliationClaim.STILL_UNKNOWN,
    }
    assert get_args(SandboxDispatchRequest.model_fields["method"].annotation) == (
        "POST",
    )
    assert REQUEST_TIMEOUT_SECONDS == 5
    assert get_args(
        SandboxRecoveryResult.model_fields[
            "external_effect_retry_permitted"
        ].annotation
    ) == (False,)


def test_dedicated_proof_workflow_keeps_controlled_claim_boundary() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "reproducible-decision-to-effect-e2e.yml"
    ).read_text(encoding="utf-8")
    assert 'report["controlled_decision_to_effect_e2e_proven"] is True' in workflow
    assert 'report["production_decision_to_effect_e2e_proven"] is False' in workflow
    assert 'report["trustlog_exactly_once_proven"] is False' in workflow
    assert 'report["production_validation_proven"] is False' in workflow
    assert 'report["fault"]["transport_calls"] == 1' in workflow


def test_freeze_docs_and_historical_stop_record_are_consistent() -> None:
    en = (
        ROOT
        / "docs"
        / "en"
        / "architecture"
        / "controlled-execution-proof-architecture-freeze-v1.md"
    ).read_text(encoding="utf-8")
    ja = (
        ROOT
        / "docs"
        / "ja"
        / "architecture"
        / "controlled-execution-proof-architecture-freeze-v1.md"
    ).read_text(encoding="utf-8")
    stop = (
        ROOT / "artifacts" / "real-decision-to-effect-e2e" / "STOP.md"
    ).read_text(encoding="utf-8")

    for document in (en, ja):
        assert "FROZEN CONTROLLED PROOF SCOPE" in document
        assert ANCHOR in document
        assert "reproducible-decision-to-effect-e2e" in document

    assert "Historical Stop Record" in stop
    assert "superseded for the controlled CI proof scope" in stop
