"""Reproducible policy-gated reconciliation-capable execution profile proof.

This proof is separate from the frozen Controlled Execution Proof v1. It reuses
that proof's controlled /v1/decide, TLS, PostgreSQL, reconciliation, receipt and
recovery helpers while requiring authoritative reconciliation capability before
native v2 authorization consumption.

All decisions, credentials, keys and external effects are synthetic.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from veritas_os.governance.reconciliation_capability_evidence import (
    ApprovedReconciliationCapabilityVerifier,
    ReconciliationCapabilityClass,
    ReconciliationCapabilityEvidence,
    ReconciliationCapabilityVerificationResult,
    ReconciliationCapabilityVerifierTrustPolicy,
    verify_reconciliation_capability_evidence_to_proof,
)
from veritas_os.policy import native_bind_authorization_consumption as consumption
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
)
from veritas_os.policy.native_bind_authorization import _verified_source
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.db import close_pool
from veritas_os.tests import test_decision_to_effect_controlled_e2e as base
from veritas_os.tests.helpers.proof_provenance import capture_proof_provenance
from veritas_os.tests.test_native_bind_authorization_consumption import _fresh

pytestmark = [
    pytest.mark.slow,
    pytest.mark.postgresql,
    pytest.mark.skipif(
        os.getenv("VERITAS_RECONCILIATION_CAPABLE_PROFILE_E2E") != "1",
        reason="reconciliation-capable execution profile proof workflow only",
    ),
]

NORMAL_PAYLOAD = {
    "event_id": "42345678-1234-4234-8234-123456789abc",
    "message": "reconciliation-capable profile normal",
}
FAULT_PAYLOAD = {
    "event_id": "42345678-1234-4234-8234-123456789abd",
    "message": "reconciliation-capable profile lost-response fault",
}
BLOCKED_PAYLOAD = {
    "event_id": "42345678-1234-4234-8234-123456789abe",
    "message": "reconciliation-capable profile blocked",
}

POLICY_ID = "reconciliation-capable-execution-profile/v1"
VERIFIER_ID = "reconciliation-capability-verifier/profile-proof-v1"
VERIFIER_POLICY_ID = "reconciliation-capability-policy/profile-proof-v1"
TRUST_POLICY_ID = "reconciliation-capability-trust/profile-proof-v1"
VERIFIER_POLICY_HASH = sha256_of_canonical_json(
    {
        "domain": "veritas.reconciliation-capability-verifier-policy/v1",
        "verifier_id": VERIFIER_ID,
        "policy_id": VERIFIER_POLICY_ID,
        "accepted_classes": [
            ReconciliationCapabilityClass.AUTHORITATIVE_QUERY.value,
            ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE.value,
        ],
    }
)


class ControlledCapabilityVerifier:
    """CI-only verifier representing the deployment-owned capability seam."""

    def verify(
        self,
        evidence: ReconciliationCapabilityEvidence,
    ) -> ReconciliationCapabilityVerificationResult:
        evidence_digest = evidence.deterministic_digest()
        material = sha256_of_canonical_json(
            {
                "domain": "veritas.controlled-capability-verification/v1",
                "evidence_digest": evidence_digest,
                "verifier_id": VERIFIER_ID,
                "verifier_policy_id": VERIFIER_POLICY_ID,
                "verifier_policy_hash": VERIFIER_POLICY_HASH,
            }
        )
        return ReconciliationCapabilityVerificationResult(
            verified=True,
            evidence_digest=evidence_digest,
            verifier_id=VERIFIER_ID,
            verifier_policy_id=VERIFIER_POLICY_ID,
            verifier_policy_hash=VERIFIER_POLICY_HASH,
            verification_material_digest=material,
            semantic_consistent=True,
            reason="controlled-profile-verification",
        )


def _verifier_trust_policy() -> ReconciliationCapabilityVerifierTrustPolicy:
    return ReconciliationCapabilityVerifierTrustPolicy(
        policy_id=TRUST_POLICY_ID,
        approved_verifiers=(
            ApprovedReconciliationCapabilityVerifier(
                verifier_id=VERIFIER_ID,
                verifier_policy_id=VERIFIER_POLICY_ID,
                verifier_policy_hash=VERIFIER_POLICY_HASH,
            ),
        ),
    )


def _verified_capability_proof(
    evidence: ReconciliationCapabilityEvidence,
    *,
    verified_at: datetime,
    trust_policy: ReconciliationCapabilityVerifierTrustPolicy,
):
    return verify_reconciliation_capability_evidence_to_proof(
        evidence,
        verifier=ControlledCapabilityVerifier(),
        trust_policy=trust_policy,
        verified_at=verified_at,
    )


def _target_configuration_digest(case: dict[str, Any]) -> str:
    return sha256_of_canonical_json(
        {
            "domain": "veritas.reconciliation-capable-target/v1",
            "deployment": asdict(case["deployment"]),
        }
    )


def _current_inputs(case: dict[str, Any], now: datetime):
    inputs = case["inputs"]
    risk, source = _fresh(inputs, now)
    governance = replace(inputs["governance_inputs"], verification_now=now)
    _, _, context = _verified_source(risk, source, governance)
    return risk, source, context


def _capability_evidence(
    case: dict[str, Any],
    *,
    now: datetime,
    capability_class: ReconciliationCapabilityClass,
    endpoint_digest: str | None = None,
    target_configuration_digest: str | None = None,
    verifier_id: str = VERIFIER_ID,
    verifier_policy_id: str = VERIFIER_POLICY_ID,
    verifier_policy_hash: str = VERIFIER_POLICY_HASH,
    valid_until: datetime | None = None,
) -> ReconciliationCapabilityEvidence:
    _, _, context = _current_inputs(case, now)
    config_digest = target_configuration_digest or _target_configuration_digest(case)
    endpoint = endpoint_digest or context.endpoint_identity_binding_digest

    authoritative_query = (
        capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_QUERY
    )
    authoritative_evidence = (
        capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE
    )
    authoritative = authoritative_query or authoritative_evidence

    source_digest = sha256_of_canonical_json(
        {
            "domain": "veritas.reconciliation-capability-source/v1",
            "target_id": case["deployment"].target_system,
            "endpoint_identity_binding_digest": endpoint,
            "target_configuration_digest": config_digest,
            "lookup_semantics": "exact-idempotency-key-read-only",
        }
    )

    return ReconciliationCapabilityEvidence(
        evidence_id=(
            "rce-profile:"
            + hashlib.sha256(
                (
                    case["artifact"].authorization_id
                    + ":"
                    + capability_class.value
                    + ":"
                    + now.isoformat()
                ).encode("utf-8")
            ).hexdigest()
        ),
        target_id=case["deployment"].target_system,
        endpoint_identity_binding_digest=endpoint,
        target_configuration_digest=config_digest,
        capability_class=capability_class,
        correlation_identity_type="idempotency_key" if authoritative_query else None,
        correlation_identity_pre_dispatch=authoritative_query,
        correlation_identity_caller_controlled=authoritative_query,
        exact_attempt_lookup_available=authoritative_query,
        exact_lineage_binding_supported=authoritative,
        downstream_durability_supported=authoritative,
        non_mutating_observation_supported=authoritative,
        authoritative_evidence_available=authoritative_evidence,
        source_type="controlled_profile_capability_assessment",
        source_identity="controlled-sandbox-profile-v1",
        source_digest=source_digest,
        verifier_id=verifier_id if authoritative else None,
        verifier_policy_id=verifier_policy_id if authoritative else None,
        verifier_policy_hash=verifier_policy_hash if authoritative else None,
        assessed_at=(now - timedelta(seconds=1)).isoformat(),
        valid_until=(valid_until or (now + timedelta(minutes=5))).isoformat(),
        metadata={
            "controlled_fixture": True,
            "production_claim": False,
            "profile": POLICY_ID,
        },
    )


def _required_policy(
    case: dict[str, Any],
    evidence: ReconciliationCapabilityEvidence,
    trust_policy: ReconciliationCapabilityVerifierTrustPolicy,
) -> consumption.ReconciliationCapabilityExecutionPolicy:
    return consumption.ReconciliationCapabilityExecutionPolicy(
        policy_id=POLICY_ID,
        require_authoritative_reconciliation=True,
        current_target_configuration_digest=_target_configuration_digest(case),
        expected_verifier_id=VERIFIER_ID,
        expected_verifier_policy_id=VERIFIER_POLICY_ID,
        expected_verifier_policy_hash=VERIFIER_POLICY_HASH,
        expected_evidence_digest=evidence.deterministic_digest(),
        expected_trust_policy_id=trust_policy.policy_id,
        expected_trust_policy_hash=trust_policy.deterministic_hash(),
    )


async def _consume_with_required_capability(
    case: dict[str, Any],
    gate_capture: dict[str, dict[str, Any]],
):
    artifact = case["artifact"]
    inputs = case["inputs"]
    store = PostgresAtomicAuthorizationConsumptionStore()
    consume_at = datetime.now(UTC)
    current_risk, current_source, _ = _current_inputs(case, consume_at)
    evidence = _capability_evidence(
        case,
        now=consume_at,
        capability_class=ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
    )
    trust_policy = _verifier_trust_policy()
    proof = _verified_capability_proof(
        evidence,
        verified_at=consume_at,
        trust_policy=trust_policy,
    )
    policy = _required_policy(case, evidence, trust_policy)

    result = await consumption.consume_native_bind_authorization(
        artifact,
        issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        current_source_inputs=current_source,
        current_runtime_risk_packet=current_risk,
        now=consume_at,
        consumption_store=store,
        reconciliation_capability_policy=policy,
        reconciliation_capability_proof=proof,
        reconciliation_capability_trust_policy=trust_policy,
    )
    assert result.reconciliation_capability_required is True
    assert result.reconciliation_capability_satisfied is True
    assert result.reconciliation_capability_policy_id == POLICY_ID
    assert (
        result.reconciliation_capability_evidence_digest
        == evidence.deterministic_digest()
    )

    gate_capture[artifact.authorization_id] = {
        "policy": asdict(policy),
        "capability_evidence": evidence.model_dump(mode="json"),
        "verified_capability_proof": proof.model_dump(mode="json"),
        "result": {
            "authorization_consumed": result.authorization_consumed,
            "reconciliation_capability_required": (
                result.reconciliation_capability_required
            ),
            "reconciliation_capability_satisfied": (
                result.reconciliation_capability_satisfied
            ),
            "reconciliation_capability_policy_id": (
                result.reconciliation_capability_policy_id
            ),
            "reconciliation_capability_evidence_digest": (
                result.reconciliation_capability_evidence_digest
            ),
            "reconciliation_capability_verification_proof_hash": (
                result.reconciliation_capability_verification_proof_hash
            ),
            "execution_authority_created": result.execution_authority_created,
            "external_action_executed": result.external_action_executed,
        },
    }
    return store, result.consumption_record


async def _assert_blocked_before_consumption(
    case: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    artifact = case["artifact"]
    inputs = case["inputs"]
    store = PostgresAtomicAuthorizationConsumptionStore()
    now = datetime.now(UTC)
    current_risk, current_source, _ = _current_inputs(case, now)
    trust_policy = _verifier_trust_policy()

    authoritative = _capability_evidence(
        case,
        now=now,
        capability_class=ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
    )
    if mode == "missing":
        evidence = authoritative
        proof = None
        policy = _required_policy(case, authoritative, trust_policy)
        expected_reason = (
            "NABC_RECONCILIATION_CAPABILITY_VERIFIED_PROOF_REQUIRED"
        )
        capability_class = None
        evidence_digest = None
        proof_hash = None
    elif mode == "heuristic":
        evidence = _capability_evidence(
            case,
            now=now,
            capability_class=ReconciliationCapabilityClass.HEURISTIC_ONLY,
        )
        proof = _verified_capability_proof(
            evidence,
            verified_at=now,
            trust_policy=trust_policy,
        )
        policy = _required_policy(case, evidence, trust_policy)
        expected_reason = "NABC_RECONCILIATION_CAPABILITY_REJECTED"
        capability_class = evidence.capability_class.value
        evidence_digest = evidence.deterministic_digest()
        proof_hash = proof.verification_proof_hash
    else:
        raise AssertionError(f"unsupported blocked mode: {mode}")

    with pytest.raises(
        consumption.NativeAuthorizationConsumptionError,
        match=expected_reason,
    ) as exc_info:
        await consumption.consume_native_bind_authorization(
            artifact,
            issuance_source_inputs=inputs["source_inputs"],
            governance_inputs=inputs["governance_inputs"],
            trust_inputs=inputs["trust_inputs"],
            current_source_inputs=current_source,
            current_runtime_risk_packet=current_risk,
            now=now,
            consumption_store=store,
            reconciliation_capability_policy=policy,
            reconciliation_capability_proof=proof,
            reconciliation_capability_trust_policy=trust_policy,
        )

    stored = await store.get(artifact.authorization_id)
    assert stored is None
    assert str(exc_info.value) == expected_reason

    return {
        "mode": mode,
        "reason": expected_reason,
        "authorization_id": artifact.authorization_id,
        "authorization_consumed": False,
        "consumption_record_present": False,
        "network_dispatch_entered": False,
        "capability_class": capability_class,
        "capability_evidence_digest": evidence_digest,
        "verification_proof_hash": proof_hash,
        "policy": asdict(policy),
        "trust_policy_id": trust_policy.policy_id,
        "trust_policy_hash": trust_policy.deterministic_hash(),
    }


def _profile_case_evidence(
    case: dict[str, Any],
    result: dict[str, Any],
    gate_capture: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evidence = base._case_evidence(case, result)
    evidence["reconciliation_capability_gate"] = gate_capture[
        case["artifact"].authorization_id
    ]
    return evidence


@pytest.mark.asyncio
async def test_reproducible_reconciliation_capable_execution_profile(
    tmp_path,
    monkeypatch,
):
    provenance = capture_proof_provenance(
        source_sha=os.environ.get("VERITAS_PROFILE_SOURCE_SHA", ""),
        base_sha=os.environ.get("VERITAS_PROFILE_BASE_SHA", ""),
        expected_tested_sha=os.environ.get("VERITAS_PROFILE_TESTED_SHA", ""),
    )

    ca_path = Path(os.environ["VERITAS_SANDBOX_CA_FILE"])
    ca_pem = ca_path.read_text()
    writer_token = os.environ["VERITAS_SANDBOX_WRITER_TOKEN"]
    reader_token = os.environ["VERITAS_SANDBOX_READER_TOKEN"]
    outage_flag = Path(os.environ["VERITAS_SANDBOX_LOOKUP_OUTAGE_FLAG"])
    report_path = Path(os.environ["VERITAS_RECONCILIATION_PROFILE_REPORT"])
    evidence_path = Path(os.environ["VERITAS_RECONCILIATION_PROFILE_EVIDENCE"])
    assert writer_token != reader_token

    rows_before = await base._sandbox_row_count()

    blocked_case = base._build_decision_case(
        tmp_path / "blocked",
        BLOCKED_PAYLOAD,
    )
    blocked_rows_before = await base._sandbox_row_count()
    blocked_missing = await _assert_blocked_before_consumption(
        blocked_case,
        mode="missing",
    )
    blocked_heuristic = await _assert_blocked_before_consumption(
        blocked_case,
        mode="heuristic",
    )
    blocked_rows_after = await base._sandbox_row_count()
    assert blocked_rows_after == blocked_rows_before

    gate_capture: dict[str, dict[str, Any]] = {}

    async def gated_consume(case):
        return await _consume_with_required_capability(case, gate_capture)

    monkeypatch.setattr(base, "_consume", gated_consume)

    normal_case = base._build_decision_case(tmp_path / "normal", NORMAL_PAYLOAD)
    normal = await base._run_normal_case(
        normal_case,
        ca_pem=ca_pem,
        writer_token=writer_token,
        reader_token=reader_token,
    )
    rows_after_normal = await base._sandbox_row_count()
    assert rows_after_normal == rows_before + 1

    fault_case = base._build_decision_case(tmp_path / "fault", FAULT_PAYLOAD)
    fault = await base._run_fault_case(
        fault_case,
        ca_pem=ca_pem,
        writer_token=writer_token,
        reader_token=reader_token,
        outage_flag=outage_flag,
    )
    rows_after_fault = await base._sandbox_row_count()
    assert rows_after_fault == rows_before + 2

    migration = await base._migration_head()
    assert migration == "0009"

    normal_gate = gate_capture[normal_case["artifact"].authorization_id]
    fault_gate = gate_capture[fault_case["artifact"].authorization_id]

    evidence = {
        "format_version": "reconciliation-capable-execution-evidence/v1",
        **provenance,
        "profile_id": POLICY_ID,
        "blocked": {
            "missing": blocked_missing,
            "heuristic": blocked_heuristic,
        },
        "normal": _profile_case_evidence(normal_case, normal, gate_capture),
        "fault": _profile_case_evidence(fault_case, fault, gate_capture),
    }
    evidence_hash = sha256_of_canonical_json(evidence)

    proof_conjunction = {
        "current_head_source_recorded": True,
        "tested_checkout_sha_verified": True,
        "real_decide_route_exercised": True,
        "policy_requires_authoritative_reconciliation": (
            normal_gate["result"]["reconciliation_capability_required"]
            and fault_gate["result"]["reconciliation_capability_required"]
        ),
        "authoritative_query_satisfied_before_consumption": (
            normal_gate["result"]["reconciliation_capability_satisfied"]
            and fault_gate["result"]["reconciliation_capability_satisfied"]
            and normal_gate["capability_evidence"]["capability_class"]
            == ReconciliationCapabilityClass.AUTHORITATIVE_QUERY.value
            and fault_gate["capability_evidence"]["capability_class"]
            == ReconciliationCapabilityClass.AUTHORITATIVE_QUERY.value
        ),
        "runtime_sealed_capability_proof_required": (
            normal_gate["result"][
                "reconciliation_capability_verification_proof_hash"
            ]
            == normal_gate["verified_capability_proof"][
                "verification_proof_hash"
            ]
            and fault_gate["result"][
                "reconciliation_capability_verification_proof_hash"
            ]
            == fault_gate["verified_capability_proof"][
                "verification_proof_hash"
            ]
        ),
        "missing_capability_rejected_before_consumption": (
            blocked_missing["authorization_consumed"] is False
            and blocked_missing["consumption_record_present"] is False
        ),
        "heuristic_capability_rejected_before_consumption": (
            blocked_heuristic["authorization_consumed"] is False
            and blocked_heuristic["consumption_record_present"] is False
        ),
        "blocked_path_never_entered_network_dispatch": (
            blocked_missing["network_dispatch_entered"] is False
            and blocked_heuristic["network_dispatch_entered"] is False
            and blocked_rows_after == blocked_rows_before
        ),
        "real_postgresql_consumption_after_gate": True,
        "real_certificate_validated_tls_post_after_gate": (
            normal["dispatch"].reason_code == "HTTP_201_MATCHING_ACK"
            and fault["transport_delegate_observation"] == "HTTP_201_MATCHING_ACK"
        ),
        "effect_unknown_semantics_preserved": (
            normal["state_after_dispatch"].state
            == base.EffectExecutionState.EFFECT_UNKNOWN
            and fault["state_after_dispatch"].state
            == base.EffectExecutionState.EFFECT_UNKNOWN
            and fault["unavailable"].state
            == base.EffectExecutionState.EFFECT_UNKNOWN
        ),
        "read_only_reconciliation_preserved": (
            normal["recovered"].state
            == base.EffectExecutionState.CONFIRMED_EFFECT
            and fault["recovered"].state
            == base.EffectExecutionState.CONFIRMED_EFFECT
        ),
        "no_blind_redispatch_preserved": (
            fault["transport_calls"] == 1
            and fault["unavailable"].external_effect_retry_permitted is False
        ),
        "receipt_outcome_lineage_preserved": (
            normal["recovered"].receipt_bundle is not None
            and fault["recovered"].receipt_bundle is not None
        ),
    }
    profile_proven = all(proof_conjunction.values())

    report_body = {
        "format_version": "reconciliation-capable-execution-profile-proof/v1",
        "result": "PASS" if profile_proven else "FAIL",
        "proof": "CONTROLLED_RECONCILIATION_CAPABLE_EXECUTION_PROFILE_V1",
        "production_claim": False,
        **provenance,
        "profile_id": POLICY_ID,
        "endpoint": base.deployment().endpoint_url,
        "deployment_hash": sha256_of_canonical_json(asdict(base.deployment())),
        "ca_sha256": hashlib.sha256(ca_path.read_bytes()).hexdigest(),
        "alembic_head": migration,
        "blocked": {
            "missing_reason": blocked_missing["reason"],
            "missing_authorization_consumed": False,
            "heuristic_reason": blocked_heuristic["reason"],
            "heuristic_authorization_consumed": False,
            "sandbox_rows_added": blocked_rows_after - blocked_rows_before,
        },
        "normal": {
            "decision_id": normal_case["cda"].decision_id,
            "authorization_id": normal_case["artifact"].authorization_id,
            "capability_class": normal_gate["capability_evidence"]["capability_class"],
            "capability_evidence_digest": (
                normal_gate["result"]["reconciliation_capability_evidence_digest"]
            ),
            "verification_proof_hash": normal_gate["result"][
                "reconciliation_capability_verification_proof_hash"
            ],
            "consumption_id": normal["consumption"].consumption_id,
            "dispatch_reason": normal["dispatch"].reason_code,
            "terminal_effect_state": normal["recovered"].state.value,
            "receipt_bundle_hash": normal["recovered"].receipt_bundle.bundle_hash,
        },
        "fault": {
            "decision_id": fault_case["cda"].decision_id,
            "authorization_id": fault_case["artifact"].authorization_id,
            "capability_class": fault_gate["capability_evidence"]["capability_class"],
            "capability_evidence_digest": (
                fault_gate["result"]["reconciliation_capability_evidence_digest"]
            ),
            "verification_proof_hash": fault_gate["result"][
                "reconciliation_capability_verification_proof_hash"
            ],
            "consumption_id": fault["consumption"].consumption_id,
            "dispatch_reason": fault["dispatch"].reason_code,
            "lookup_outage_state": fault["unavailable"].state.value,
            "lookup_outage_retry_permitted": (
                fault["unavailable"].external_effect_retry_permitted
            ),
            "terminal_effect_state": fault["recovered"].state.value,
            "transport_calls": fault["transport_calls"],
            "receipt_bundle_hash": fault["recovered"].receipt_bundle.bundle_hash,
        },
        "sandbox_rows_added_by_valid_paths": rows_after_fault - rows_before,
        "evidence_hash": evidence_hash,
        "proof_conjunction": proof_conjunction,
        "controlled_policy_gated_reconciliation_profile_proven": profile_proven,
        "production_reconciliation_capability_proven": False,
        "universal_downstream_reconcilability_proven": False,
        "exactly_once_external_delivery_proven": False,
        "production_validation_proven": False,
        "proof_non_claims": [
            "production readiness",
            "real customer credentials",
            "real customer endpoint",
            "universal downstream reconcilability",
            "exactly-once external delivery",
            "external UTC production trust",
            "regulatory approval or certification",
        ],
    }
    report = {
        **report_body,
        "proof_manifest_hash": sha256_of_canonical_json(report_body),
    }

    evidence_serialized = json.dumps(evidence, indent=2, sort_keys=True)
    report_serialized = json.dumps(report, indent=2, sort_keys=True)
    for secret in (writer_token, reader_token):
        assert secret not in evidence_serialized
        assert secret not in report_serialized

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(evidence_serialized + "\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_serialized + "\n")

    assert profile_proven is True
    await close_pool()
