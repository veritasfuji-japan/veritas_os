from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    EffectExecutionState,
    EffectStateTrackingConsumptionStore,
    InMemoryAtomicEffectStateStore,
    ReconciliationClaim,
    ReconciliationEvidence,
    classify_completed_bind_attempt,
    reconcile_effect_unknown,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    BindAuthorizationConsumptionResult,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.trusted_https_reconciliation import (
    ApprovedReconciliationVerifier,
    ReconciliationVerifierPolicy,
    TrustedHttpsReconciliationError,
    TrustedHttpsReconciliationVerifier,
    TrustedReconciliationEndpoint,
    reconciliation_observation_digest,
)
from veritas_os.security.hash import sha256_of_canonical_json

ACK = {
    "operation_id": "consumption-1",
    "external_operation_reference": "external-1",
    "status": "committed",
    "source_identity": "trusted-ledger",
    "authorization_id": "authorization-1",
    "consumption_id": "consumption-1",
}


class _Response:
    def __init__(self, payload: Any = ACK, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://ledger.example.test")

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "failed",
                request=self.request,
                response=httpx.Response(self.status_code),
            )


class _Client:
    response = _Response()
    error: Exception | None = None
    last_url = ""
    kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).kwargs = kwargs

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _Response:
        del kwargs
        type(self).last_url = url
        if self.error is not None:
            raise self.error
        return self.response


@dataclass(frozen=True)
class _Receipt:
    pass


def _endpoint(**changes: Any) -> TrustedReconciliationEndpoint:
    values = {
        "scheme": "https",
        "host": "ledger.example.test",
        "port": 8443,
        "path_prefix": "/v1/effects",
        "source_type": "external_https_api",
        "source_identity": "trusted-ledger",
    }
    values.update(changes)
    return TrustedReconciliationEndpoint(**values)


def _verifier(
    *, endpoint: TrustedReconciliationEndpoint | None = None, approved: bool = True
) -> TrustedHttpsReconciliationVerifier:
    endpoint = endpoint or _endpoint()
    policy_hash = TrustedHttpsReconciliationVerifier.policy_hash_for_config(
        endpoint=endpoint, verifier_id="reconciliation-verifier-1"
    )
    if not approved:
        policy_hash = "0" * 64
    return TrustedHttpsReconciliationVerifier(
        endpoint=endpoint,
        verifier_id="reconciliation-verifier-1",
        verifier_policy=ReconciliationVerifierPolicy(
            (ApprovedReconciliationVerifier("reconciliation-verifier-1", policy_hash),)
        ),
    )


def _evidence(**changes: Any) -> ReconciliationEvidence:
    values = {
        "operation_id": "consumption-1",
        "authorization_id": "authorization-1",
        "consumption_id": "consumption-1",
        "claim": ReconciliationClaim.CONFIRMED_EFFECT,
        "source_type": "external_https_api",
        "source_identity": "trusted-ledger",
        "observed_at": "2026-08-26T12:00:00+00:00",
        "external_operation_reference": "external-1",
        "external_ack_digest": sha256_of_canonical_json(ACK),
        "observation_digest": "0" * 64,
    }
    values.update(changes)
    provisional = ReconciliationEvidence(**values)
    if "observation_digest" not in changes:
        values["observation_digest"] = reconciliation_observation_digest(provisional)
    return ReconciliationEvidence(**values)


@pytest.fixture(autouse=True)
def _http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _Client.response = _Response()
    _Client.error = None
    _Client.last_url = ""
    monkeypatch.setattr(
        "veritas_os.policy.trusted_https_reconciliation.httpx.AsyncClient", _Client
    )


@pytest.mark.asyncio
async def test_valid_acknowledgement_is_independently_verified() -> None:
    evidence = _evidence()
    verified = await _verifier().verify(evidence)

    assert verified.evidence == evidence
    assert verified.verifier_id == "reconciliation-verifier-1"
    assert _Client.last_url == (
        "https://ledger.example.test:8443/v1/effects/external-1"
    )
    assert _Client.kwargs["follow_redirects"] is False
    context = _Client.kwargs["verify"]
    assert context.check_hostname is True
    assert context.verify_mode.name == "CERT_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"external_operation_reference": "wrong"}, "OPERATION_REFERENCE"),
        ({"external_ack_digest": "a" * 64}, "ACK_DIGEST"),
        ({"observation_digest": "b" * 64}, "OBSERVATION_DIGEST"),
        ({"source_identity": "attacker"}, "SOURCE_IDENTITY"),
        ({"source_type": "caller_object"}, "SOURCE_TYPE"),
        ({"observed_at": "not-a-time"}, "OBSERVED_AT"),
        ({"observed_at": "2026-08-26T12:00:00"}, "OBSERVED_AT"),
    ],
)
async def test_untrusted_evidence_fails_closed(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(TrustedHttpsReconciliationError, match=message):
        await _verifier().verify(_evidence(**changes))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"malformed": True}, "ACK_RETRIEVAL"),
        ({**ACK, "external_operation_reference": "wrong"}, "OPERATION_REFERENCE"),
        ({**ACK, "source_identity": "wrong"}, "SOURCE_IDENTITY"),
        ({**ACK, "status": "invented"}, "STATUS_UNSUPPORTED"),
        ({**ACK, "status": "rejected"}, "CLAIM_CONTRADICTED"),
        ({**ACK, "authorization_id": "wrong"}, "AUTHORIZATION_LINEAGE"),
        ({**ACK, "consumption_id": "wrong"}, "CONSUMPTION_LINEAGE"),
    ],
)
async def test_untrusted_acknowledgement_fails_closed(
    payload: dict[str, Any], message: str
) -> None:
    _Client.response = _Response(payload)
    with pytest.raises(TrustedHttpsReconciliationError, match=message):
        await _verifier().verify(_evidence())


@pytest.mark.asyncio
async def test_tls_or_network_failure_fails_closed() -> None:
    request = httpx.Request("GET", "https://ledger.example.test")
    _Client.error = httpx.ConnectError("certificate verify failed", request=request)
    with pytest.raises(TrustedHttpsReconciliationError, match="ACK_RETRIEVAL"):
        await _verifier().verify(_evidence())


def test_endpoint_substitution_and_unapproved_policy_fail_closed() -> None:
    with pytest.raises(TrustedHttpsReconciliationError, match="ENDPOINT_INVALID"):
        _verifier(endpoint=_endpoint(scheme="http"))
    with pytest.raises(TrustedHttpsReconciliationError, match="ENDPOINT_INVALID"):
        _verifier(endpoint=_endpoint(host="trusted.test@attacker.test"))
    with pytest.raises(TrustedHttpsReconciliationError, match="VERIFIER_NOT_APPROVED"):
        _verifier(approved=False)


@pytest.mark.asyncio
async def test_production_verifier_reconciles_effect_unknown() -> None:
    consumption = build_authorization_consumption_record(
        live_adapter_bind_authorization_id="authorization-1",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key="idem-1",
        bind_context_hash="b" * 64,
        execution_intent_id="intent-1",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-26T11:59:00+00:00",
    )
    authorization_store = InMemoryAtomicAuthorizationConsumptionStore()
    effect_store = InMemoryAtomicEffectStateStore()
    tracking_store = EffectStateTrackingConsumptionStore(
        authorization_store, effect_store
    )
    assert await tracking_store.consume_once(consumption)
    await classify_completed_bind_attempt(
        result=BindAuthorizationConsumptionResult(
            consumption_record=consumption,
            bind_receipt=_Receipt(),  # type: ignore[arg-type]
            adapter_apply_attempted=True,
        ),
        effect_store=effect_store,
        updated_at="2026-08-26T12:00:00+00:00",
    )

    acknowledgement = {
        **ACK,
        "operation_id": consumption.consumption_id,
        "consumption_id": consumption.consumption_id,
    }
    _Client.response = _Response(acknowledgement)

    terminal = await reconcile_effect_unknown(
        operation_id=consumption.consumption_id,
        evidence=_evidence(
            operation_id=consumption.consumption_id,
            consumption_id=consumption.consumption_id,
            external_ack_digest=sha256_of_canonical_json(acknowledgement),
        ),
        verifier=_verifier(),
        effect_store=effect_store,
        updated_at="2026-08-26T12:01:00+00:00",
    )
    assert terminal.state == EffectExecutionState.CONFIRMED_EFFECT


@pytest.mark.asyncio
async def test_failed_verification_cannot_confirm_effect() -> None:
    consumption = build_authorization_consumption_record(
        live_adapter_bind_authorization_id="authorization-1",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key="idem-2",
        bind_context_hash="b" * 64,
        execution_intent_id="intent-1",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-26T11:59:00+00:00",
    )
    effect_store = InMemoryAtomicEffectStateStore()
    tracking_store = EffectStateTrackingConsumptionStore(
        InMemoryAtomicAuthorizationConsumptionStore(), effect_store
    )
    assert await tracking_store.consume_once(consumption)
    await classify_completed_bind_attempt(
        result=BindAuthorizationConsumptionResult(
            consumption_record=consumption,
            bind_receipt=_Receipt(),  # type: ignore[arg-type]
            adapter_apply_attempted=True,
        ),
        effect_store=effect_store,
        updated_at="2026-08-26T12:00:00+00:00",
    )
    evidence = _evidence(
        operation_id=consumption.consumption_id,
        consumption_id=consumption.consumption_id,
        observation_digest="f" * 64,
    )
    with pytest.raises(BindEffectStateError, match="VERIFICATION_FAILED"):
        await reconcile_effect_unknown(
            operation_id=consumption.consumption_id,
            evidence=evidence,
            verifier=_verifier(),
            effect_store=effect_store,
            updated_at="2026-08-26T12:01:00+00:00",
        )
    state = await effect_store.get(consumption.consumption_id)
    assert state is not None
    assert state.state == EffectExecutionState.EFFECT_UNKNOWN
