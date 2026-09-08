"""Independent read-only sandbox lookup and fail-closed effect confirmation.

No POST, consumption, execution claim, receipt or authorization is created.
Historical authorization inputs and current read-only credential policy are
separate trust inputs. A dispatch acknowledgement is never accepted as input.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
import re
import ssl
from typing import Any, Callable

from pydantic import SecretBytes

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState, EffectStateRecord, InMemoryAtomicEffectStateStore,
    PostgresAtomicEffectStateStore, ReconciliationClaim, ReconciliationEvidence,
    VerifiedReconciliationEvidence, _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _timestamp
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore, PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs, RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import (
    NativeAuthorizationSourceInputs, _verified_source, verify_native_bind_authorization,
)
from veritas_os.policy.sandbox_action_binding import SandboxDeployment, verify_sandbox_action_binding
from veritas_os.policy.sandbox_credential_resolution import (
    SandboxCredentialProvider, SandboxCredentialRequest, SandboxProviderCredential, _validate_metadata,
)
from veritas_os.policy.sandbox_event_store import parse_event, validate_key
from veritas_os.policy.sandbox_https_transport import _parse_operation, _read_bounded_response
from veritas_os.policy.sandbox_pre_effect import SandboxClockReading, _clock
from veritas_os.policy.trusted_https_reconciliation import (
    ReconciliationVerifierPolicy, reconciliation_observation_digest,
)
from veritas_os.security.hash import sha256_of_canonical_json

VERIFIER_ID = "sandbox-readonly-reconciliation/v1"
LOOKUP_SCOPE = "sandbox.operation.lookup.v1"


class SandboxReconciliationError(ValueError):
    """No inferred outcome; original consumption and execution attempt remain."""


@dataclass(frozen=True)
class SandboxReaderPolicy:
    """Current operator configuration, independent of the execution credential.

    The provider must enforce read-only scope and a distinct principal/material.
    Different references alone cannot prove separation inside a dishonest provider.
    """

    credential_reference_id: str
    credential_version: str
    credential_provider_type: str
    credential_environment: str
    ca_pem: str | None = None


def sandbox_reconciliation_policy_hash(deployment: SandboxDeployment, reader: SandboxReaderPolicy) -> str:
    """Approval digest for exact endpoint, action pins, reader and CA configuration."""
    return sha256_of_canonical_json({
        "verifier": VERIFIER_ID, "deployment": asdict(deployment), "reader": asdict(reader),
        "scope": LOOKUP_SCOPE, "method": "GET", "path": "/v1/operations",
        "timeout_seconds": 5, "header_limit": 8192, "body_limit": 4096,
        "interpretation": "matching-persisted-event-only/v1",
    })


@dataclass(frozen=True)
class SandboxReconciliationResult:
    """Local record and independently retrieved evidence, not a Receipt/Outcome.

    Existing effect storage persists the evidence digest. Callers must retain the
    full returned evidence in their audit pipeline; durable evidence archival and
    atomic Receipt/Outcome publication are not implemented by this result.
    """

    record: EffectStateRecord
    evidence: VerifiedReconciliationEvidence | None


async def reconcile_sandbox_effect(
    authorization: Any, payload_json: str, *, deployment: SandboxDeployment,
    issuance_source_inputs: NativeAuthorizationSourceInputs,
    historical_governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    consumption_store: PostgresAtomicAuthorizationConsumptionStore | InMemoryAtomicAuthorizationConsumptionStore,
    effect_store: PostgresAtomicEffectStateStore | InMemoryAtomicEffectStateStore,
    reader_policy: SandboxReaderPolicy, verifier_policy: ReconciliationVerifierPolicy,
    provider: SandboxCredentialProvider, trusted_clock: Callable[[], SandboxClockReading],
    allow_in_memory_for_testing: bool = False,
) -> SandboxReconciliationResult:
    """Rebuild original lineage, independently GET by key, then CAS confirmation.

    Historical governance/source inputs are operator-controlled archived inputs,
    never embedded snapshots or a packet-selected clock. They verify the original
    grant, not permission to execute now. Current reader metadata and clock govern
    lookup. Authorization expiry does not itself erase evidence of an earlier effect.
    Non-200 stays unknown; invalid evidence/errors raise without state changes.
    Confirmation is relative to the trusted sandbox/provider, not independent of
    their operator. A failed/ambiguous CAS never returns a confirmed result.
    """
    response = material = token = wire = None
    writer = None
    cancelled = False
    try:
        durable = (type(consumption_store) is PostgresAtomicAuthorizationConsumptionStore
                   and type(effect_store) is PostgresAtomicEffectStateStore)
        if not durable and not (
            allow_in_memory_for_testing is True
            and type(consumption_store) is InMemoryAtomicAuthorizationConsumptionStore
            and type(effect_store) is InMemoryAtomicEffectStateStore
        ):
            raise ValueError("durable stores")
        if type(reader_policy) is not SandboxReaderPolicy or provider is None:
            raise ValueError("reader policy")
        if any(type(v) is not str or not v or v != v.strip() for k, v in asdict(reader_policy).items() if k != "ca_pem"):
            raise ValueError("reader fields")
        if reader_policy.credential_reference_id == deployment.credential_reference_id:
            raise ValueError("writer reference")
        policy_hash = sandbox_reconciliation_policy_hash(deployment, reader_policy)
        if type(verifier_policy) is not ReconciliationVerifierPolicy or not verifier_policy.approves(VERIFIER_ID, policy_hash):
            raise ValueError("unapproved policy")
        binding = verify_sandbox_action_binding(
            authorization, payload_json, deployment=deployment, source_inputs=issuance_source_inputs,
            governance_inputs=historical_governance_inputs, trust_inputs=trust_inputs,
        )
        verified = verify_native_bind_authorization(
            authorization, source_inputs=issuance_source_inputs,
            governance_inputs=historical_governance_inputs, trust_inputs=trust_inputs,
        )
        _, _, context = _verified_source(
            verified.source_runtime_risk_packet, issuance_source_inputs, historical_governance_inputs,
        )
        started = trusted_clock()
        now = _clock(started)
        stored = await consumption_store.get(verified.authorization_id)
        if stored is None:
            raise ValueError("missing consumption")
        expected = build_authorization_consumption_record(
            live_adapter_bind_authorization_id=verified.authorization_id,
            live_adapter_bind_authorization_hash=verified.authorization_hash,
            idempotency_key=verified.idempotency_key, bind_context_hash=verified.bind_context_hash,
            execution_intent_id=verified.execution_intent_id, execution_intent_hash=verified.execution_intent_hash,
            endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
            credential_reference_digest=context.credential_reference_digest,
            credential_scope_binding_digest=context.credential_scope_binding_digest, consumed_at=stored.consumed_at,
        )
        consumed_at = datetime.fromisoformat(_timestamp(stored.consumed_at))
        if stored != expected or not (
            datetime.fromisoformat(verified.valid_from) <= consumed_at < datetime.fromisoformat(verified.valid_until)
            and consumed_at <= now
        ):
            raise ValueError("consumption lineage")
        current = await effect_store.get(stored.consumption_id)
        if current is None:
            raise ValueError("missing attempt")
        expected_current = _build_record(
            consumption=stored, state=EffectExecutionState.EFFECT_UNKNOWN, revision=2,
            updated_at=current.updated_at,
            reason_code="SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
        )
        if current != expected_current or not consumed_at <= datetime.fromisoformat(_timestamp(current.updated_at)) <= now:
            raise ValueError("dispatch lineage")
        origin = deployment.endpoint_url.removesuffix("/v1/events")
        host = origin.removeprefix("https://")
        request = SandboxCredentialRequest(
            verified.authorization_id, current.operation_id,
            reader_policy.credential_reference_id, reader_policy.credential_provider_type,
            reader_policy.credential_version, LOOKUP_SCOPE, reader_policy.credential_environment, origin,
        )
        async with asyncio.timeout(5):
            description = await provider.describe(request)
            metadata = _validate_metadata(description, request, started, trusted_clock())
            digest = sha256_of_canonical_json(metadata.model_dump(mode="json"))
            response = await provider.resolve(request, expected_metadata_digest=digest)
            if type(response) is not SandboxProviderCredential or type(response.material) is not SecretBytes:
                raise ValueError("provider response")
            if _validate_metadata(response.metadata, request, started, trusted_clock()) != metadata:
                raise ValueError("substituted credential")
            tls = ssl.create_default_context(cadata=reader_policy.ca_pem)
            tls.minimum_version = ssl.TLSVersion.TLSv1_2
            tls.set_alpn_protocols(["http/1.1"])
            key = validate_key(current.idempotency_key)
            prefix = (f"GET /v1/operations?idempotency_key={key} HTTP/1.1\r\n"
                      f"Host: {host}\r\nConnection: close\r\nAuthorization: Bearer ").encode("ascii")
            stream, writer = await asyncio.open_connection(
                host, 443, ssl=tls, server_hostname=host, limit=8192, ssl_handshake_timeout=5,
            )
            _validate_metadata(metadata, request, started, trusted_clock())
            material = response.material
            token = material.get_secret_value()
            if not 32 <= len(token) <= 4096 or not re.fullmatch(rb"[A-Za-z0-9._~+/-]+=*", token):
                raise ValueError("token")
            wire = prefix + token + b"\r\n\r\n"
            writer.write(wire)
            material = response = token = wire = None
            await writer.drain()
            status, headers, raw = await _read_bounded_response(stream)
            if status != 200:
                return SandboxReconciliationResult(current, None)
            operation = _parse_operation(headers, raw)
            event = parse_event(binding.binding.payload_json.encode("utf-8"))
            if (operation.idempotency_key != current.idempotency_key
                    or operation.event_id != event.event_id
                    or operation.payload_digest != binding.binding.payload_digest):
                raise ValueError("external binding")
            finished = trusted_clock()
            _validate_metadata(metadata, request, started, finished)
        observed_at = _timestamp(finished.now)
        values = dict(
            operation_id=current.operation_id, authorization_id=current.authorization_id,
            consumption_id=current.consumption_id, claim=ReconciliationClaim.CONFIRMED_EFFECT,
            source_type="sandbox-readonly-https", source_identity=origin, observed_at=observed_at,
            external_operation_reference=operation.operation_id,
            external_ack_digest=sha256_of_canonical_json(operation.model_dump(mode="json")),
        )
        evidence = ReconciliationEvidence(**values, observation_digest="0" * 64)
        evidence = evidence.model_copy(update={"observation_digest": reconciliation_observation_digest(evidence)})
        proof = VerifiedReconciliationEvidence(
            evidence=evidence, verifier_id=VERIFIER_ID, verifier_policy_hash=policy_hash,
            verification_proof_hash=sha256_of_canonical_json({
                "observation": evidence.model_dump(mode="json"), "policy_hash": policy_hash,
                "original_record_hash": current.record_hash, "reader_metadata_digest": digest,
            }), verified_at=observed_at,
        )
        record = _build_record(
            consumption=stored, state=EffectExecutionState.CONFIRMED_EFFECT,
            revision=current.revision + 1, updated_at=observed_at,
            reason_code="SANDBOX_READONLY_LOOKUP_CONFIRMED",
            reconciliation_evidence_hash=proof.deterministic_digest(),
        )
        if await effect_store.get(current.operation_id) != current:
            raise ValueError("changed attempt")
        if not verifier_policy.approves(VERIFIER_ID, policy_hash):
            raise ValueError("withdrawn policy")
        if await effect_store.transition(
            operation_id=current.operation_id, expected_state=EffectExecutionState.EFFECT_UNKNOWN, record=record,
        ) is not True or await effect_store.get(current.operation_id) != record:
            raise ValueError("confirmation not durable")
        return SandboxReconciliationResult(record, proof)
    except asyncio.CancelledError:
        cancelled = True
    except Exception:
        pass
    finally:
        response = material = token = wire = None
        if writer is not None:
            try:
                writer.transport.abort()
            except Exception:
                pass
    if cancelled:
        raise asyncio.CancelledError()
    raise SandboxReconciliationError("SR_RECONCILIATION_FAILED_NO_RETRY")
