"""Controlled real-TLS + real-PostgreSQL composition for native v2 sandbox.

This test is opt-in and runs only in the dedicated CI composition workflow.
Native issuance remains a deterministic signed synthetic fixture. The network,
TLS handshake, sender/reader credential separation, PostgreSQL stores, sandbox
receiver persistence, reconciliation and receipt publication are exercised for
real inside the isolated runner environment.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import time

import psycopg
import pytest
from pydantic import SecretBytes

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    PostgresAtomicEffectStateStore,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
)
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
from veritas_os.tests.test_native_bind_authorization_consumption import _fresh
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD, deployment
from veritas_os.tests.test_sandbox_action_binding_integration import issued as issued_fixture

issued = issued_fixture

pytestmark = [
    pytest.mark.slow,
    pytest.mark.postgresql,
    pytest.mark.skipif(
        os.getenv("VERITAS_SANDBOX_COMPOSITION") != "1",
        reason="controlled native-v2 sandbox composition workflow only",
    ),
]


def _clock() -> SandboxClockReading:
    now = datetime.now(UTC)
    return SandboxClockReading(
        now=now,
        monotonic_seconds=time.monotonic(),
        health_checked_at=now,
        uncertainty_seconds=0.05,
    )


class ControlledCredentialProvider:
    """CI-only provider that binds one synthetic token to the exact request."""

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
        # Recheck the request against the stored metadata before material access.
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
    """Delegate one real TLS POST, then simulate response loss at the caller."""

    def __init__(self, delegate: SandboxHTTPSTransport) -> None:
        self._delegate = delegate
        self.delegate_observation = None
        self.calls = 0

    async def send_once(self, request, *, take_material):
        self.calls += 1
        self.delegate_observation = await self._delegate.send_once(
            request,
            take_material=take_material,
        )
        raise RuntimeError("controlled lost response after remote commit")


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


@pytest.mark.asyncio
async def test_native_v2_controlled_composition_lost_response_lookup_outage_then_recovery(issued):
    artifact, inputs = issued
    config = deployment()
    ca_path = Path(os.environ["VERITAS_SANDBOX_CA_FILE"])
    ca_pem = ca_path.read_text()
    writer_token = os.environ["VERITAS_SANDBOX_WRITER_TOKEN"]
    reader_token = os.environ["VERITAS_SANDBOX_READER_TOKEN"]
    outage_flag = Path(os.environ["VERITAS_SANDBOX_LOOKUP_OUTAGE_FLAG"])
    report_path = Path(os.environ["VERITAS_SANDBOX_COMPOSITION_REPORT"])

    assert writer_token != reader_token
    assert config.endpoint_url == "https://sandbox.example.invalid/v1/events"

    consumption_store = PostgresAtomicAuthorizationConsumptionStore()
    effect_store = PostgresAtomicEffectStateStore()

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
        consumption_store=consumption_store,
    )
    consumption = consumed.consumption_record

    def load_current(now: datetime) -> SandboxCurrentInputs:
        risk, source = _fresh(inputs, now)
        return SandboxCurrentInputs(
            source=source,
            governance=inputs["governance_inputs"],
            runtime_risk_packet=risk,
        )

    writer_provider = ControlledCredentialProvider(writer_token)
    real_transport = SandboxHTTPSTransport(
        endpoint_url=config.endpoint_url,
        ca_pem=ca_pem,
    )
    transport = LoseObservedResponseTransport(real_transport)

    dispatch = await execute_sandbox_bind(
        artifact,
        json.dumps(PAYLOAD),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        trusted_clock=_clock,
        load_current_inputs=load_current,
        provider=writer_provider,
        transport=transport,
    )

    after_dispatch = await effect_store.get(consumption.consumption_id)
    assert after_dispatch is not None
    assert after_dispatch.state == EffectExecutionState.EFFECT_UNKNOWN
    assert transport.calls == 1
    assert transport.delegate_observation == "HTTP_201_MATCHING_ACK"
    assert dispatch.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
    assert await _sandbox_row_count() == 1

    reader_policy = SandboxReaderPolicy(
        credential_reference_id="controlled-ci-reader",
        credential_version="1",
        credential_provider_type="CONTROLLED_CI_PROVIDER",
        credential_environment="sandbox",
        ca_pem=ca_pem,
    )
    verifier_policy = ReconciliationVerifierPolicy(
        (
            ApprovedReconciliationVerifier(
                VERIFIER_ID,
                sandbox_reconciliation_policy_hash(config, reader_policy),
            ),
        )
    )
    reader_provider = ControlledCredentialProvider(reader_token)

    outage_flag.parent.mkdir(parents=True, exist_ok=True)
    outage_flag.touch()
    try:
        unavailable = await recover_sandbox_attempt(
            artifact,
            json.dumps(PAYLOAD),
            deployment=config,
            issuance_source_inputs=inputs["source_inputs"],
            historical_governance_inputs=inputs["governance_inputs"],
            trust_inputs=inputs["trust_inputs"],
            consumption_store=consumption_store,
            effect_store=effect_store,
            reader_policy=reader_policy,
            verifier_policy=verifier_policy,
            provider=reader_provider,
            trusted_clock=_clock,
        )
        assert unavailable.recovery_status == "STILL_UNKNOWN"
        assert unavailable.state == EffectExecutionState.EFFECT_UNKNOWN
        assert unavailable.external_effect_retry_permitted is False
        assert await _sandbox_row_count() == 1
    finally:
        outage_flag.unlink(missing_ok=True)

    recovered = await recover_sandbox_attempt(
        artifact,
        json.dumps(PAYLOAD),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        historical_governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        reader_policy=reader_policy,
        verifier_policy=verifier_policy,
        provider=reader_provider,
        trusted_clock=_clock,
    )
    assert recovered.recovery_status == "CONFIRMED_EFFECT"
    assert recovered.state == EffectExecutionState.CONFIRMED_EFFECT
    assert recovered.external_effect_retry_permitted is False
    assert recovered.receipt_bundle is not None
    assert await _sandbox_row_count() == 1

    writer_calls_after_effect = transport.calls
    reader_calls_after_confirmation = reader_provider.describe_calls

    repeated = await recover_sandbox_attempt(
        artifact,
        json.dumps(PAYLOAD),
        deployment=config,
        issuance_source_inputs=inputs["source_inputs"],
        historical_governance_inputs=inputs["governance_inputs"],
        trust_inputs=inputs["trust_inputs"],
        consumption_store=consumption_store,
        effect_store=effect_store,
        reader_policy=reader_policy,
        verifier_policy=verifier_policy,
        provider=reader_provider,
        trusted_clock=_clock,
    )
    assert repeated == recovered
    assert transport.calls == writer_calls_after_effect == 1
    assert reader_provider.describe_calls == reader_calls_after_confirmation
    assert await _sandbox_row_count() == 1

    archive = await effect_store.get_reconciliation(consumption.consumption_id)
    assert archive is not None
    migration = await _migration_head()
    assert migration == "0008"

    report = {
        "format_version": "native-v2-sandbox-controlled-composition/v1",
        "result": "PASS",
        "proof": "CONTROLLED_NATIVE_V2_SANDBOX_TLS_POSTGRES_COMPOSITION",
        "production_claim": False,
        "decision_lineage_source": "SIGNED_SYNTHETIC_NATIVE_FIXTURE",
        "endpoint": config.endpoint_url,
        "deployment_hash": sha256_of_canonical_json(asdict(config)),
        "ca_sha256": hashlib.sha256(ca_path.read_bytes()).hexdigest(),
        "main_postgresql": True,
        "sandbox_postgresql": True,
        "alembic_head": migration,
        "real_tls_transport": True,
        "writer_reader_credentials_distinct": writer_token != reader_token,
        "authorization_consumed": True,
        "dispatch_intent_state": after_dispatch.state.value,
        "controlled_lost_response": True,
        "transport_delegate_observation": transport.delegate_observation,
        "lookup_outage_state": unavailable.state.value,
        "lookup_outage_retry_permitted": unavailable.external_effect_retry_permitted,
        "terminal_effect_state": recovered.state.value,
        "external_event_rows": await _sandbox_row_count(),
        "external_operation_reference": archive.operation.operation_id,
        "reconciliation_evidence_hash": archive.proof.deterministic_digest(),
        "receipt_bundle_hash": recovered.receipt_bundle.bundle_hash,
        "no_blind_redispatch": transport.calls == 1,
        "repeat_recovery_avoids_lookup": reader_provider.describe_calls == reader_calls_after_confirmation,
        "trustlog_exactly_once_proven": False,
        "real_decision_to_effect_e2e_proven": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    await close_pool()
