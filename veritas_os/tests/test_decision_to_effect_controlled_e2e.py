"""Current-head controlled Decision-to-Effect E2E proof.

This opt-in proof starts at the actual /v1/decide route with controlled model
output, verifies the CanonicalDecisionArtifact, promotes the exact chosen sandbox
action, issues a native v2 authorization through the existing source chain, and
then reuses the merged real-TLS / real-PostgreSQL sandbox composition.

It is a reproducible controlled proof, not a production deployment. All action
payloads, credentials, keys and external effects are synthetic.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import psycopg
import pytest
from pydantic import SecretBytes

from veritas_os.governance.canonical_decision_artifact import (
    verify_canonical_decision_artifact,
)
from veritas_os.policy import sandbox_action_binding as binding
from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    PostgresAtomicEffectStateStore,
)
from veritas_os.policy.canonical_verified_decision_promotion import (
    build_canonical_verified_decision_promotion_packet,
    canonical_verified_decision_promotion_proof,
    verify_canonical_verified_decision_promotion_packet,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
)
from veritas_os.policy.native_bind_authorization import verify_native_bind_authorization
from veritas_os.policy.native_bind_authorization_consumption import (
    consume_native_bind_authorization,
)
from veritas_os.policy.sandbox_bind_execution import execute_sandbox_bind
from veritas_os.policy.sandbox_credential_resolution import (
    SandboxCredentialMetadata,
    SandboxProviderCredential,
)
from veritas_os.policy.sandbox_https_transport import SandboxHTTPSTransport
from veritas_os.policy.sandbox_pre_effect import SandboxClockReading, SandboxCurrentInputs
from veritas_os.policy.sandbox_reconciliation import (
    SandboxReaderPolicy,
    VERIFIER_ID,
    sandbox_reconciliation_policy_hash,
)
from veritas_os.policy.sandbox_recovery import recover_sandbox_attempt
from veritas_os.policy.trusted_https_reconciliation import (
    ApprovedReconciliationVerifier,
    ReconciliationVerifierPolicy,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.db import close_pool, get_pool
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_credential_authorization as credentials,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_endpoint_allowlist as endpoints,
)
from veritas_os.tests.helpers.native_approval_source import build_native_authority_source
from veritas_os.tests.test_native_bind_authorization import _setup
from veritas_os.tests.test_native_bind_authorization_consumption import _fresh
from veritas_os.tests.test_sandbox_action_binding import contract, deployment

pytestmark = [
    pytest.mark.slow,
    pytest.mark.postgresql,
    pytest.mark.skipif(
        os.getenv("VERITAS_DECISION_TO_EFFECT_E2E") != "1",
        reason="controlled Decision-to-Effect E2E workflow only",
    ),
]

NORMAL_PAYLOAD = {
    "event_id": "32345678-1234-4234-8234-123456789abc",
    "message": "controlled decision-to-effect normal",
}
FAULT_PAYLOAD = {
    "event_id": "32345678-1234-4234-8234-123456789abd",
    "message": "controlled decision-to-effect lost-response fault",
}


def _clock() -> SandboxClockReading:
    now = datetime.now(UTC)
    return SandboxClockReading(
        now=now,
        monotonic_seconds=time.monotonic(),
        health_checked_at=now,
        uncertainty_seconds=0.05,
    )


class ControlledCredentialProvider:
    """CI-only provider binding one synthetic token to an exact request."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._metadata: SandboxCredentialMetadata | None = None
        self.describe_calls = 0
        self.resolve_calls = 0

    async def describe(self, request):
        self.describe_calls += 1
        now = datetime.now(UTC)
        self._metadata = SandboxCredentialMetadata(
            credential_reference_id=request.credential_reference_id,
            credential_provider_type=request.credential_provider_type,
            credential_version=request.credential_version,
            credential_scope=request.credential_scope,
            credential_environment=request.credential_environment,
            audience=request.audience,
            credential_kind="bearer",
            valid_from=(now - timedelta(minutes=2)).isoformat(),
            valid_until=(now + timedelta(minutes=5)).isoformat(),
            observed_at=now.isoformat(),
            revoked=False,
        )
        return self._metadata

    async def resolve(self, request, *, expected_metadata_digest):
        self.resolve_calls += 1
        if self._metadata is None:
            raise RuntimeError("descriptor required")
        if expected_metadata_digest != sha256_of_canonical_json(
            self._metadata.model_dump(mode="json")
        ):
            raise RuntimeError("descriptor digest mismatch")
        for name in (
            "credential_reference_id",
            "credential_provider_type",
            "credential_version",
            "credential_scope",
            "credential_environment",
            "audience",
        ):
            if getattr(request, name) != getattr(self._metadata, name):
                raise RuntimeError("request changed")
        return SandboxProviderCredential(
            metadata=self._metadata,
            material=SecretBytes(self._token.encode("ascii")),
        )


class LoseObservedResponseTransport:
    """Perform one real POST, then model caller-side response loss."""

    def __init__(self, delegate: SandboxHTTPSTransport) -> None:
        self._delegate = delegate
        self.delegate_observation: str | None = None
        self.calls = 0

    async def send_once(self, request, *, take_material):
        self.calls += 1
        self.delegate_observation = await self._delegate.send_once(
            request,
            take_material=take_material,
        )
        raise RuntimeError("controlled response loss after remote commit")


def _build_decision_case(case_dir: Path, payload: dict[str, str]) -> dict[str, Any]:
    """Capture /v1/decide, verify CDA/promotion, then issue exact native v2 auth."""

    case_dir.mkdir(parents=True, exist_ok=True)
    output = case_dir / "decision-capture.json"
    config = deployment()
    action_contract = contract()
    action_binding = binding.build_sandbox_action_binding(
        json.dumps(payload),
        deployment=config,
        expected_contract=action_contract,
    )
    overrides = {
        "intended_action": binding.ACTION,
        "target_system": config.target_system,
        "target_resource": config.endpoint_url,
        "evidence_refs": [action_binding.reference],
    }
    code = (
        "import json,sys; from pathlib import Path; "
        "from veritas_os.tests.helpers.live_decision_capture import capture; "
        "capture(Path(sys.argv[1]), candidate_overrides=json.loads(sys.argv[2]))"
    )
    subprocess.run(
        [sys.executable, "-c", code, str(output), json.dumps(overrides)],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        timeout=180,
        capture_output=True,
        text=True,
    )
    captured = json.loads(output.read_text())
    assert captured["pipeline_ok"] is True
    assert captured["infrastructure_calls"]["kms_sign_calls"] > 0
    assert captured["infrastructure_calls"]["object_lock_put_calls"] > 0

    verification = verify_canonical_decision_artifact(
        captured["canonical_decision_artifact"]
    )
    assert verification.is_valid and verification.artifact is not None
    cda = verification.artifact

    promoted_at = datetime.fromisoformat(captured["observed_at"])
    promotion = build_canonical_verified_decision_promotion_packet(
        captured["canonical_decision_artifact"],
        captured["candidate"],
        promoted_at=promoted_at,
        ttl_seconds=300,
        expected_state_fingerprint="synthetic:sandbox:empty",
    )
    verified_promotion = verify_canonical_verified_decision_promotion_packet(promotion)
    promotion_proof = canonical_verified_decision_promotion_proof(verified_promotion)
    assert promotion_proof["canonical_decision_verified"] is True
    assert promotion_proof["decision_lineage_proven"] is True
    assert promotion_proof["execution_intent_lineage_proven"] is True

    # Adapt only synthetic fixture metadata. Production source/crypto verifiers
    # and all promotion/native issuance builders execute unchanged.
    original_endpoint = endpoints._candidate
    original_reference = credentials._reference
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            endpoints,
            "_candidate",
            lambda **kw: original_endpoint(
                **kw,
                endpoint_host="sandbox.example.invalid",
                endpoint_path_prefix="/v1/events",
            ),
        )
        patch.setattr(
            credentials,
            "_reference",
            lambda **kw: original_reference(
                **kw,
                credential_scope=config.credential_scope,
                credential_environment=config.credential_environment,
            ),
        )
        source = build_native_authority_source(promotion, promoted_at)

    artifact, inputs, *_ = _setup(source, action_contract, promoted_at)
    verified_authorization = verify_native_bind_authorization(artifact, **inputs)
    assert verified_authorization == artifact
    assert artifact.execution_intent == promotion.exact_execution_intent
    assert artifact.execution_intent_id == promotion.execution_intent_id
    assert artifact.execution_intent_hash == promotion.execution_intent_hash
    assert artifact.execution_intent["decision_id"] == cda.decision_id
    assert artifact.execution_intent["decision_hash"] == cda.decision_hash
    assert artifact.execution_intent["decision_ts"] == cda.decision_ts

    return {
        "payload": payload,
        "captured": captured,
        "cda": cda,
        "promotion": promotion,
        "promotion_proof": promotion_proof,
        "artifact": artifact,
        "inputs": inputs,
        "deployment": config,
        "action_binding": action_binding,
    }


async def _sandbox_row_count() -> int:
    dsn = os.environ["VERITAS_SANDBOX_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    conn = await psycopg.AsyncConnection.connect(dsn)
    try:
        cur = await conn.execute("SELECT count(*) FROM sandbox_events")
        return int((await cur.fetchone())[0])
    finally:
        await conn.close()


async def _migration_head() -> str:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT version_num FROM alembic_version")
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("missing alembic version")
    return str(row[0])


def _load_current(inputs):
    calls = {"count": 0}

    def load(now: datetime) -> SandboxCurrentInputs:
        calls["count"] += 1
        risk, source = _fresh(inputs, now)
        return SandboxCurrentInputs(
            source=source,
            governance=inputs["governance_inputs"],
            runtime_risk_packet=risk,
        )

    return load, calls


def _reader_inputs(config, ca_pem: str, token: str, suffix: str):
    policy = SandboxReaderPolicy(
        credential_reference_id=f"controlled-e2e-reader-{suffix}",
        credential_version="1",
        credential_provider_type="CONTROLLED_CI_PROVIDER",
        credential_environment="sandbox",
        ca_pem=ca_pem,
    )
    verifier = ReconciliationVerifierPolicy(
        (
            ApprovedReconciliationVerifier(
                VERIFIER_ID,
                sandbox_reconciliation_policy_hash(config, policy),
            ),
        )
    )
    return policy, verifier, ControlledCredentialProvider(token)


async def _consume(case):
    artifact = case["artifact"]
    inputs = case["inputs"]
    store = PostgresAtomicAuthorizationConsumptionStore()
    consume_at = datetime.now(UTC)
    current_risk, current_source = _fresh(inputs, consume_at)
    consumed = await consume_native_bind_authorization(
        artifact,
        issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        current_source_inputs=current_source,
        current_runtime_risk_packet=current_risk,
        now=consume_at,
        consumption_store=store,
    )
    return store, consumed.consumption_record


def _assert_receipt_decision_lineage(case, bundle) -> None:
    cda = case["cda"]
    promotion = case["promotion"]
    bind_receipt = bundle.bind_receipt
    outcome = bundle.outcome_receipt
    assert bind_receipt["decision_id"] == cda.decision_id
    assert bind_receipt["decision_hash"] == cda.decision_hash
    assert bind_receipt["execution_intent_id"] == promotion.execution_intent_id
    assert bind_receipt["execution_intent_hash"] == promotion.execution_intent_hash
    assert outcome["decision_id"] == cda.decision_id
    assert outcome["execution_intent_id"] == promotion.execution_intent_id
    assert outcome["bind_receipt_id"] == bind_receipt["bind_receipt_id"]


async def _run_normal_case(case, *, ca_pem: str, writer_token: str, reader_token: str):
    artifact, inputs, config = case["artifact"], case["inputs"], case["deployment"]
    consumption_store, consumption = await _consume(case)
    effect_store = PostgresAtomicEffectStateStore()
    writer = ControlledCredentialProvider(writer_token)
    transport = SandboxHTTPSTransport(endpoint_url=config.endpoint_url, ca_pem=ca_pem)
    load_current, governance_calls = _load_current(inputs)

    dispatch = await execute_sandbox_bind(
        artifact,
        json.dumps(case["payload"]),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        trusted_clock=_clock,
        load_current_inputs=load_current,
        provider=writer,
        transport=transport,
    )
    state = await effect_store.get(consumption.consumption_id)
    assert state is not None and state.state == EffectExecutionState.EFFECT_UNKNOWN
    assert dispatch.reason_code == "HTTP_201_MATCHING_ACK"

    reader_policy, verifier_policy, reader = _reader_inputs(
        config,
        ca_pem,
        reader_token,
        "normal",
    )
    recovered = await recover_sandbox_attempt(
        artifact,
        json.dumps(case["payload"]),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        historical_governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        reader_policy=reader_policy,
        verifier_policy=verifier_policy,
        provider=reader,
        trusted_clock=_clock,
    )
    assert recovered.state == EffectExecutionState.CONFIRMED_EFFECT
    assert recovered.recovery_status == "CONFIRMED_EFFECT"
    assert recovered.external_effect_retry_permitted is False
    assert recovered.receipt_bundle is not None
    _assert_receipt_decision_lineage(case, recovered.receipt_bundle)
    archive = await effect_store.get_reconciliation(consumption.consumption_id)
    assert archive is not None
    return {
        "dispatch": dispatch,
        "state_after_dispatch": state,
        "recovered": recovered,
        "archive": archive,
        "consumption": consumption,
        "reader_calls": reader.describe_calls,
        "governance_recheck_calls": governance_calls["count"],
    }


async def _run_fault_case(
    case,
    *,
    ca_pem: str,
    writer_token: str,
    reader_token: str,
    outage_flag: Path,
):
    artifact, inputs, config = case["artifact"], case["inputs"], case["deployment"]
    consumption_store, consumption = await _consume(case)
    effect_store = PostgresAtomicEffectStateStore()
    writer = ControlledCredentialProvider(writer_token)
    transport = LoseObservedResponseTransport(
        SandboxHTTPSTransport(endpoint_url=config.endpoint_url, ca_pem=ca_pem)
    )
    load_current, governance_calls = _load_current(inputs)

    dispatch = await execute_sandbox_bind(
        artifact,
        json.dumps(case["payload"]),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        trusted_clock=_clock,
        load_current_inputs=load_current,
        provider=writer,
        transport=transport,
    )
    state = await effect_store.get(consumption.consumption_id)
    assert state is not None and state.state == EffectExecutionState.EFFECT_UNKNOWN
    assert dispatch.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
    assert transport.delegate_observation == "HTTP_201_MATCHING_ACK"
    assert transport.calls == 1

    reader_policy, verifier_policy, reader = _reader_inputs(
        config,
        ca_pem,
        reader_token,
        "fault",
    )
    outage_flag.parent.mkdir(parents=True, exist_ok=True)
    outage_flag.touch()
    try:
        unavailable = await recover_sandbox_attempt(
            artifact,
            json.dumps(case["payload"]),
            deployment=config,
            issuance_source_inputs=inputs["source_inputs"],
            historical_governance_inputs=inputs["governance_inputs"],
            trust_inputs=inputs["trust_inputs"],
            consumption_store=consumption_store,
            effect_store=effect_store,
            reader_policy=reader_policy,
            verifier_policy=verifier_policy,
            provider=reader,
            trusted_clock=_clock,
        )
        assert unavailable.state == EffectExecutionState.EFFECT_UNKNOWN
        assert unavailable.recovery_status == "STILL_UNKNOWN"
        assert unavailable.external_effect_retry_permitted is False
        assert transport.calls == 1
    finally:
        outage_flag.unlink(missing_ok=True)

    recovered = await recover_sandbox_attempt(
        artifact,
        json.dumps(case["payload"]),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        historical_governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        reader_policy=reader_policy,
        verifier_policy=verifier_policy,
        provider=reader,
        trusted_clock=_clock,
    )
    assert recovered.state == EffectExecutionState.CONFIRMED_EFFECT
    assert recovered.recovery_status == "CONFIRMED_EFFECT"
    assert recovered.receipt_bundle is not None
    _assert_receipt_decision_lineage(case, recovered.receipt_bundle)
    reader_calls_after_confirmation = reader.describe_calls

    repeated = await recover_sandbox_attempt(
        artifact,
        json.dumps(case["payload"]),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        historical_governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        reader_policy=reader_policy,
        verifier_policy=verifier_policy,
        provider=reader,
        trusted_clock=_clock,
    )
    assert repeated == recovered
    assert transport.calls == 1
    assert reader.describe_calls == reader_calls_after_confirmation

    archive = await effect_store.get_reconciliation(consumption.consumption_id)
    assert archive is not None
    return {
        "dispatch": dispatch,
        "state_after_dispatch": state,
        "unavailable": unavailable,
        "recovered": recovered,
        "repeated": repeated,
        "archive": archive,
        "consumption": consumption,
        "transport_calls": transport.calls,
        "transport_delegate_observation": transport.delegate_observation,
        "reader_calls_after_confirmation": reader_calls_after_confirmation,
        "reader_calls_after_repeat": reader.describe_calls,
        "governance_recheck_calls": governance_calls["count"],
    }


def _case_evidence(case, result) -> dict[str, Any]:
    return {
        "canonical_decision_artifact": case["cda"].model_dump(mode="json"),
        "promotion_packet": case["promotion"].model_dump(mode="json"),
        "native_authorization": case["artifact"].model_dump(mode="json"),
        "consumption": result["consumption"].model_dump(mode="json"),
        "reconciliation_archive": result["archive"].model_dump(mode="json"),
        "receipt_bundle": result["recovered"].receipt_bundle.model_dump(mode="json"),
    }


@pytest.mark.asyncio
async def test_current_head_decision_to_effect_normal_and_fault_e2e(tmp_path):
    source_sha = os.environ.get("VERITAS_E2E_SOURCE_SHA", "")
    base_sha = os.environ.get("VERITAS_E2E_BASE_SHA", "")
    assert re.fullmatch(r"[0-9a-f]{40}", source_sha)
    assert re.fullmatch(r"[0-9a-f]{40}", base_sha)

    ca_path = Path(os.environ["VERITAS_SANDBOX_CA_FILE"])
    ca_pem = ca_path.read_text()
    writer_token = os.environ["VERITAS_SANDBOX_WRITER_TOKEN"]
    reader_token = os.environ["VERITAS_SANDBOX_READER_TOKEN"]
    outage_flag = Path(os.environ["VERITAS_SANDBOX_LOOKUP_OUTAGE_FLAG"])
    report_path = Path(os.environ["VERITAS_DECISION_TO_EFFECT_REPORT"])
    evidence_path = Path(os.environ["VERITAS_DECISION_TO_EFFECT_EVIDENCE"])
    assert writer_token != reader_token

    rows_before = await _sandbox_row_count()

    normal_case = _build_decision_case(tmp_path / "normal", NORMAL_PAYLOAD)
    normal = await _run_normal_case(
        normal_case,
        ca_pem=ca_pem,
        writer_token=writer_token,
        reader_token=reader_token,
    )
    rows_after_normal = await _sandbox_row_count()
    assert rows_after_normal == rows_before + 1

    fault_case = _build_decision_case(tmp_path / "fault", FAULT_PAYLOAD)
    fault = await _run_fault_case(
        fault_case,
        ca_pem=ca_pem,
        writer_token=writer_token,
        reader_token=reader_token,
        outage_flag=outage_flag,
    )
    rows_after_fault = await _sandbox_row_count()
    assert rows_after_fault == rows_before + 2

    migration = await _migration_head()
    assert migration == "0008"

    evidence = {
        "format_version": "controlled-decision-to-effect-evidence/v1",
        "source_sha": source_sha,
        "base_sha": base_sha,
        "normal": _case_evidence(normal_case, normal),
        "fault": _case_evidence(fault_case, fault),
    }
    evidence_hash = sha256_of_canonical_json(evidence)

    proof_conjunction = {
        "current_head_source_recorded": True,
        "real_decide_route_exercised": True,
        "canonical_decisions_verified": True,
        "selected_action_bindings_verified": True,
        "decision_lineage_proven": True,
        "execution_intent_lineage_proven": True,
        "native_v2_authorizations_verified": True,
        "real_postgresql_consumption": True,
        "current_governance_rechecks_exercised": (
            normal["governance_recheck_calls"] >= 3
            and fault["governance_recheck_calls"] >= 3
        ),
        "real_certificate_validated_tls_post": True,
        "dedicated_postgresql_effect_persistence": True,
        "read_only_reconciliation_confirmed": True,
        "bind_receipt_decision_lineage_verified": True,
        "outcome_decision_lineage_verified": True,
        "fault_unknown_preserved": (
            fault["unavailable"].state == EffectExecutionState.EFFECT_UNKNOWN
            and fault["unavailable"].external_effect_retry_permitted is False
        ),
        "no_blind_redispatch": fault["transport_calls"] == 1,
        "repeat_recovery_avoids_lookup": (
            fault["reader_calls_after_repeat"]
            == fault["reader_calls_after_confirmation"]
        ),
    }
    controlled_e2e = all(proof_conjunction.values())

    report_body = {
        "format_version": "controlled-decision-to-effect-e2e/v1",
        "result": "PASS" if controlled_e2e else "FAIL",
        "proof": "CONTROLLED_CURRENT_HEAD_DECISION_TO_EFFECT_E2E",
        "production_claim": False,
        "source_sha": source_sha,
        "base_sha": base_sha,
        "decision_capture_mode": "REAL_POST_V1_DECIDE_WITH_CONTROLLED_MODEL_OUTPUT",
        "external_effect_scope": "SYNTHETIC_SANDBOX_EVENT_PERSISTENCE",
        "endpoint": deployment().endpoint_url,
        "deployment_hash": sha256_of_canonical_json(asdict(deployment())),
        "ca_sha256": hashlib.sha256(ca_path.read_bytes()).hexdigest(),
        "alembic_head": migration,
        "normal": {
            "decision_id": normal_case["cda"].decision_id,
            "decision_hash": normal_case["cda"].decision_hash,
            "promotion_hash": normal_case["promotion"].promotion_hash,
            "authorization_id": normal_case["artifact"].authorization_id,
            "consumption_id": normal["consumption"].consumption_id,
            "dispatch_reason": normal["dispatch"].reason_code,
            "terminal_effect_state": normal["recovered"].state.value,
            "external_operation_reference": normal["archive"].operation.operation_id,
            "reconciliation_evidence_hash": normal["archive"].proof.deterministic_digest(),
            "receipt_bundle_hash": normal["recovered"].receipt_bundle.bundle_hash,
            "governance_recheck_calls": normal["governance_recheck_calls"],
        },
        "fault": {
            "decision_id": fault_case["cda"].decision_id,
            "decision_hash": fault_case["cda"].decision_hash,
            "promotion_hash": fault_case["promotion"].promotion_hash,
            "authorization_id": fault_case["artifact"].authorization_id,
            "consumption_id": fault["consumption"].consumption_id,
            "dispatch_reason": fault["dispatch"].reason_code,
            "transport_delegate_observation": fault["transport_delegate_observation"],
            "lookup_outage_state": fault["unavailable"].state.value,
            "lookup_outage_retry_permitted": fault["unavailable"].external_effect_retry_permitted,
            "terminal_effect_state": fault["recovered"].state.value,
            "external_operation_reference": fault["archive"].operation.operation_id,
            "reconciliation_evidence_hash": fault["archive"].proof.deterministic_digest(),
            "receipt_bundle_hash": fault["recovered"].receipt_bundle.bundle_hash,
            "transport_calls": fault["transport_calls"],
            "governance_recheck_calls": fault["governance_recheck_calls"],
        },
        "sandbox_rows_added": rows_after_fault - rows_before,
        "evidence_hash": evidence_hash,
        "proof_conjunction": proof_conjunction,
        "controlled_decision_to_effect_e2e_proven": controlled_e2e,
        "production_decision_to_effect_e2e_proven": False,
        "trustlog_exactly_once_proven": False,
        "production_validation_proven": False,
        "proof_non_claims": [
            "production readiness",
            "real customer credentials",
            "real customer endpoint",
            "independent production infrastructure",
            "external UTC clock trust",
            "TrustLog exactly-once publication",
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

    assert controlled_e2e is True
    await close_pool()
