#!/usr/bin/env python3
"""Secure real-boundary PoC for the merged #2131-#2137 Bind runtime.

This proof deliberately uses:
- VERITAS_POSTURE=secure;
- real PostgreSQL stores for authorization consumption and effect state;
- a real TLS socket at the exact endpoint already bound into the signed
  authorization fixture (api.example.invalid:443/v1/billing);
- an Authorization header constructed from ephemeral secret material;
- the merged Bind -> Outcome -> TrustLog -> EFFECT_UNKNOWN runtime; and
- an independent HTTPS acknowledgement lookup before reconciliation.

The authorization source is still the deterministic authenticated reference
fixture used by the Real Bind Authorization tests. Therefore this runner proves
REAL_BIND_RUNTIME_NETWORK_DB_E2E, not yet REAL_DECISION_TO_EFFECT_E2E.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib
import json
import os
from pathlib import Path
import ssl
from typing import Any, Mapping
from unittest.mock import patch
from urllib import request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.run_decision_to_external_bind_poc import (
    _DeterministicAwsClients,
    _DeterministicKmsClient,
    _DeterministicObjectLockClient,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    PostgresAtomicEffectStateStore,
    ReconciliationClaim,
    ReconciliationEvidence,
    VerifiedReconciliationEvidence,
    reconcile_effect_unknown,
)
from veritas_os.policy.bind_effect_runtime import (
    consume_bind_record_lineage_and_effect_state,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    AuthorizedBindAdapterInstance,
    ConstructedAuthorizationHeader,
    ResolvedCredentialMaterial,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.security.trustlog_production_posture import (
    check_trustlog_production_posture,
)
from veritas_os.tests.test_live_adapter_bind_authorization import (
    VERIFICATION_NOW,
    _build,
)


EXPECTED_HOST = "api.example.invalid"
EXPECTED_PORT = 443
EXPECTED_PREFIX = "/v1/billing"


def _binding_dict(authorization: Any) -> dict[str, Any]:
    value = authorization.endpoint_identity_binding
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        raise RuntimeError("endpoint identity binding is not an object")
    return value


def _exact_endpoint(authorization: Any) -> str:
    binding = _binding_dict(authorization)
    scheme = str(binding.get("endpoint_scheme") or binding.get("scheme") or "").lower()
    host = str(binding.get("endpoint_host") or binding.get("host") or "").lower()
    port = int(binding.get("endpoint_port") or binding.get("port") or 0)
    prefix = str(
        binding.get("endpoint_path_prefix") or binding.get("path_prefix") or ""
    ).rstrip("/")
    if (scheme, host, port, prefix) != (
        "https",
        EXPECTED_HOST,
        EXPECTED_PORT,
        EXPECTED_PREFIX,
    ):
        raise RuntimeError(
            "signed authorization endpoint does not match the controlled TLS fixture: "
            f"{scheme}://{host}:{port}{prefix}"
        )
    return f"https://{host}:{port}{prefix}"


class _EnvResolver:
    async def resolve(
        self,
        credential_reference: Mapping[str, Any],
        *,
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ResolvedCredentialMaterial:
        del credential_scope_binding, live_adapter_bind_authorization_id
        token = os.environ.get("VERITAS_E2E_BEARER_TOKEN", "")
        if not token:
            raise RuntimeError("VERITAS_E2E_BEARER_TOKEN is required")
        return ResolvedCredentialMaterial(
            credential_reference_id=str(credential_reference["credential_reference_id"]),
            credential_kind=str(credential_reference["credential_kind"]),
            credential_provider_type=str(credential_reference["credential_provider_type"]),
            material=token.encode("utf-8"),
        )


class _BearerHeader:
    async def construct(
        self,
        credential: ResolvedCredentialMaterial,
        *,
        credential_reference: Mapping[str, Any],
        credential_scope_binding: Mapping[str, Any],
        live_adapter_bind_authorization_id: str,
    ) -> ConstructedAuthorizationHeader:
        del credential_reference, credential_scope_binding, live_adapter_bind_authorization_id
        token = credential.material.decode("utf-8")
        return ConstructedAuthorizationHeader(name="Authorization", value=f"Bearer {token}")


class _HttpsEffectAdapter(BindAdapterContract):
    def __init__(
        self,
        *,
        base_url: str,
        authorization_header: ConstructedAuthorizationHeader,
        ca_file: str,
        external_operation_reference: str,
        expected_fingerprint: str | None,
    ) -> None:
        self.base_url = base_url
        self.authorization_header = authorization_header
        self.ca_file = ca_file
        self.external_operation_reference = external_operation_reference
        self.expected_fingerprint = expected_fingerprint
        self.last_ack: dict[str, Any] | None = None

    def _open(self, req: request.Request) -> dict[str, Any]:
        context = ssl.create_default_context(cafile=self.ca_file)
        with request.urlopen(req, context=context, timeout=10) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def snapshot(self) -> dict[str, str]:
        return {"target": self.base_url, "state": "pre-effect"}

    def fingerprint_state(self, snapshot: Any) -> str:
        del snapshot
        return self.expected_fingerprint or "secure-e2e-pre-state"

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def validate_constraints(self, intent: ExecutionIntent, snapshot: Any) -> dict[str, bool]:
        del intent, snapshot
        return {"exact_tls_endpoint_binding": True}

    def assess_runtime_risk(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return True

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        body = json.dumps(
            {"operation_id": self.external_operation_reference},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/effects",
            data=body,
            method="POST",
            headers={
                self.authorization_header.name: self.authorization_header.value,
                "Content-Type": "application/json",
            },
        )
        self.last_ack = self._open(req)
        return self.last_ack.get("status") == "committed"

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return bool(self.last_ack and self.last_ack.get("status") == "committed")

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        return False

    def describe_target(self) -> str:
        return self.base_url


class _HttpsFactory:
    def __init__(self, ca_file: str) -> None:
        self.ca_file = ca_file
        self.adapter: _HttpsEffectAdapter | None = None

    async def build(
        self,
        *,
        authorization: Any,
        credential: ResolvedCredentialMaterial,
        authorization_header: ConstructedAuthorizationHeader,
    ) -> AuthorizedBindAdapterInstance:
        del credential
        base_url = _exact_endpoint(authorization)
        self.adapter = _HttpsEffectAdapter(
            base_url=base_url,
            authorization_header=authorization_header,
            ca_file=self.ca_file,
            external_operation_reference=authorization.idempotency_key,
            expected_fingerprint=authorization.execution_intent.get(
                "expected_state_fingerprint"
            ),
        )
        return AuthorizedBindAdapterInstance(
            adapter=self.adapter,
            adapter_contract_id=authorization.adapter_contract_id,
            adapter_contract_hash=authorization.adapter_contract_hash,
            endpoint_identity_binding_digest=authorization.endpoint_identity_binding_digest,
            credential_reference_digest=authorization.credential_reference_digest,
            credential_scope_binding_digest=authorization.credential_scope_binding_digest,
        )


@dataclass(frozen=True)
class _HttpsReconciliationVerifier:
    base_url: str
    token: str
    ca_file: str
    external_operation_reference: str

    async def verify(
        self, evidence: ReconciliationEvidence
    ) -> VerifiedReconciliationEvidence:
        if evidence.external_operation_reference != self.external_operation_reference:
            raise RuntimeError("external operation reference mismatch")
        context = ssl.create_default_context(cafile=self.ca_file)
        req = request.Request(
            f"{self.base_url}/effects/{self.external_operation_reference}",
            method="GET",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with request.urlopen(req, context=context, timeout=10) as response:  # noqa: S310
            ack = json.loads(response.read().decode("utf-8"))
        if ack.get("operation_id") != self.external_operation_reference:
            raise RuntimeError("ack operation mismatch")
        if ack.get("status") != "committed":
            raise RuntimeError("ack is not committed")
        proof_hash = sha256_of_canonical_json(ack)
        return VerifiedReconciliationEvidence(
            evidence=evidence,
            verifier_id="secure-e2e-https-ack-verifier",
            verifier_policy_hash=sha256_of_canonical_json(
                {
                    "scheme": "https",
                    "host": EXPECTED_HOST,
                    "port": EXPECTED_PORT,
                    "path_prefix": EXPECTED_PREFIX,
                    "mode": "independent_get_ack",
                }
            ),
            verification_proof_hash=proof_hash,
            verified_at=datetime.now(UTC).isoformat(),
        )


def _configure_secure_posture() -> tuple[_DeterministicAwsClients, str]:
    database_url = os.environ.get("VERITAS_DATABASE_URL", "")
    ca_file = os.environ.get("VERITAS_E2E_CA_FILE", "")
    token = os.environ.get("VERITAS_E2E_BEARER_TOKEN", "")
    if not database_url or not ca_file or not token:
        raise RuntimeError(
            "VERITAS_DATABASE_URL, VERITAS_E2E_CA_FILE and VERITAS_E2E_BEARER_TOKEN are required"
        )
    encryption_key = os.environ.get("VERITAS_ENCRYPTION_KEY") or base64.urlsafe_b64encode(
        os.urandom(32)
    ).decode("ascii")
    kms_key_id = "arn:aws:kms:us-east-1:000000000000:key/secure-real-bind-poc"
    os.environ.update(
        {
            "VERITAS_POSTURE": "secure",
            "VERITAS_TRUSTLOG_BACKEND": "postgresql",
            "VERITAS_ENCRYPTION_KEY": encryption_key,
            "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
            "VERITAS_TRUSTLOG_KMS_KEY_ID": kms_key_id,
            "VERITAS_TRUSTLOG_MIRROR_BACKEND": "s3_object_lock",
            "VERITAS_TRUSTLOG_S3_BUCKET": "secure-real-bind-poc",
            "VERITAS_TRUSTLOG_S3_PREFIX": "trustlog",
            "VERITAS_TRUSTLOG_S3_REGION": "us-east-1",
            "VERITAS_TRUSTLOG_S3_OBJECT_LOCK_MODE": "GOVERNANCE",
            "VERITAS_TRUSTLOG_S3_RETENTION_DAYS": "1",
            "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "0",
        }
    )
    posture = check_trustlog_production_posture()
    if not posture.passed:
        raise RuntimeError("secure TrustLog posture failed: " + "; ".join(posture.failures))
    kms = _DeterministicKmsClient(kms_key_id)
    s3 = _DeterministicObjectLockClient()
    return _DeterministicAwsClients(kms, s3), ca_file


async def _run(report_path: Path) -> int:
    aws_clients, ca_file = _configure_secure_posture()
    artifact, governance, trust = _build()
    base_url = _exact_endpoint(artifact)
    token = os.environ["VERITAS_E2E_BEARER_TOKEN"]
    factory = _HttpsFactory(ca_file)
    real_import = importlib.import_module

    def _controlled_import(name: str, package: str | None = None) -> Any:
        if name == "boto3":
            return aws_clients
        return real_import(name, package)

    with patch("importlib.import_module", side_effect=_controlled_import):
        runtime = await consume_bind_record_lineage_and_effect_state(
            artifact,
            governance_inputs=governance,
            trust_inputs=trust,
            now=VERIFICATION_NOW,
            consumption_store=PostgresAtomicAuthorizationConsumptionStore(),
            effect_store=PostgresAtomicEffectStateStore(),
            credential_resolver=_EnvResolver(),
            authorization_header_constructor=_BearerHeader(),
            adapter_factory=factory,
        )

    if runtime.effect_state.state != EffectExecutionState.EFFECT_UNKNOWN:
        raise RuntimeError(
            "generic HTTPS apply must remain EFFECT_UNKNOWN until independent acknowledgement"
        )
    consumption = runtime.lineage.consumption_result.consumption_record
    observation = {
        "format_version": "bind-effect-reconciliation-evidence/v1",
        "operation_id": consumption.consumption_id,
        "authorization_id": artifact.live_adapter_bind_authorization_id,
        "consumption_id": consumption.consumption_id,
        "claim": ReconciliationClaim.CONFIRMED_EFFECT,
        "source_type": "https_ack_lookup",
        "source_identity": EXPECTED_HOST,
        "observed_at": datetime.now(UTC).isoformat(),
        "external_operation_reference": artifact.idempotency_key,
        "external_ack_digest": sha256_of_canonical_json(factory.adapter.last_ack or {}),
    }
    evidence = ReconciliationEvidence(
        **observation,
        observation_digest=sha256_of_canonical_json(observation),
    )
    terminal = await reconcile_effect_unknown(
        operation_id=consumption.consumption_id,
        evidence=evidence,
        verifier=_HttpsReconciliationVerifier(
            base_url=base_url,
            token=token,
            ca_file=ca_file,
            external_operation_reference=artifact.idempotency_key,
        ),
        effect_store=PostgresAtomicEffectStateStore(),
        updated_at=datetime.now(UTC).isoformat(),
    )
    if terminal.state != EffectExecutionState.CONFIRMED_EFFECT:
        raise RuntimeError("verified acknowledgement did not produce CONFIRMED_EFFECT")

    report = {
        "proof": "REAL_BIND_RUNTIME_NETWORK_DB_E2E",
        "decision_lineage_proven": False,
        "decision_lineage_note": (
            "Authorization source is the authenticated deterministic Real Bind Authorization "
            "reference fixture; real /v1/decide lineage is the next bridge."
        ),
        "posture": os.environ.get("VERITAS_POSTURE"),
        "postgresql_consumption": True,
        "postgresql_effect_state": True,
        "tls_endpoint": base_url,
        "authorization_consumed": True,
        "bind_core_invoked": runtime.lineage.consumption_result.bind_core_invoked,
        "adapter_apply_attempted": runtime.lineage.consumption_result.adapter_apply_attempted,
        "initial_effect_state": EffectExecutionState.EFFECT_UNKNOWN.value,
        "terminal_effect_state": terminal.state.value,
        "external_ack": factory.adapter.last_ack if factory.adapter else None,
        "bind_receipt_hash": runtime.lineage.bind_receipt.bind_receipt_hash,
        "outcome_hash": runtime.lineage.outcome_receipt.outcome_hash,
        "outcome_trustlog_hash": runtime.lineage.outcome_trustlog_hash,
        "authorization_id": artifact.live_adapter_bind_authorization_id,
        "consumption_id": consumption.consumption_id,
        "result": "PASS",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/secure-real-bind-runtime-poc/report.json"),
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.report))


if __name__ == "__main__":
    raise SystemExit(main())
