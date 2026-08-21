#!/usr/bin/env python3
"""Prove a secure canonical decision-to-synthetic-external-Bind lineage."""

from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from typing import Any
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.external_bind_poc.poc import (  # noqa: E402
    FIXED_TIMESTAMP,
    LocalFixture,
    SNAPSHOT,
    _adapter,
)
from scripts.run_decide_pipeline_poc import (  # noqa: E402
    FIXTURE_PATH,
    _configure_environment,
    _observed_kernel_decide,
    _request_fixture,
)
from veritas_os.governance.action_contracts import (  # noqa: E402
    ActionClassContract,
)
from veritas_os.governance.authority_evidence import (  # noqa: E402
    ApprovedAuthorityEvidenceVerifier,
    AuthorityEvidence,
    AuthorityEvidenceSignerPolicy,
    AuthorityEvidenceVerifierPolicy,
    AuthorityRevocationPolicy,
    AuthorityRevocationVerificationResult,
    VerificationResult,
    authority_signature_payload,
    verify_authority_evidence_artifact_to_proof,
)
from veritas_os.governance.authority_evidence_signing import (  # noqa: E402
    TrustedEd25519AuthorityVerifier,
)
from veritas_os.governance.canonical_decision_artifact import (  # noqa: E402
    CanonicalDecisionArtifact,
    verify_canonical_decision_artifact,
)
from veritas_os.governance.runtime_authority import (  # noqa: E402
    RuntimeAuthorityValidator,
)
from veritas_os.policy.bind_artifacts import (  # noqa: E402
    FinalOutcome,
    hash_execution_intent,
)
from veritas_os.policy.bind_core import execute_bind_adjudication  # noqa: E402
from veritas_os.policy.decision_candidate import (  # noqa: E402
    DecisionCandidate,
    try_promote_verified_canonical_decision_candidate_to_execution_intent,
)
from veritas_os.security.hash import sha256_of_canonical_json  # noqa: E402

DEFAULT_REPORT = REPO_ROOT / "artifacts/decision-to-external-bind-poc/report.json"
ACTOR = "test-actor:decision-bind-poc"
SCOPE = ["synthetic:review:create"]
POLICY_SNAPSHOT_ID = "controlled-synthetic-policy-v1"
NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


class _NotRevoked:
    """Return deterministic, current revocation evidence for the local PoC."""

    def check(
        self,
        authority_evidence_id: str,
        *,
        now: datetime,
    ) -> AuthorityRevocationVerificationResult:
        del authority_evidence_id
        return AuthorityRevocationVerificationResult(
            checked=True,
            revoked=False,
            checked_at=now.isoformat(),
            source_identity="controlled-revocation-fixture",
            source_version="1",
            source_hash="a" * 64,
            reason="not_revoked",
        )


def _action_contract() -> ActionClassContract:
    """Return a test-safe contract that does not require human approval."""
    return ActionClassContract(
        id="synthetic_external_webhook",
        version="1.0.0",
        domain="synthetic",
        action_class="post_synthetic_review",
        description="Post a harmless synthetic review to the local fixture.",
        declared_intent="Exercise the existing external Bind path.",
        allowed_scope=list(SCOPE),
        prohibited_scope=[],
        authority_sources=["controlled-authority-fixture"],
        required_evidence=[],
        evidence_freshness={},
        irreversibility={"boundary": "local_fixture_post"},
        human_approval_rules={},
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="fail_closed",
        metadata={"synthetic_only": True},
    )


def _candidate() -> DecisionCandidate:
    """Return explicit typed input; no model prose becomes authority."""
    return DecisionCandidate(
        source_model="CONTROLLED_STRUCTURED_SYNTHETIC_CANDIDATE",
        action_type="synthetic_external_webhook",
        actor_identity=ACTOR,
        target_system="local-synthetic-fixture",
        target_resource="external-bind-poc.example.test/action",
        intended_action="post_synthetic_review",
        required_authority=list(SCOPE),
        required_human_approval=False,
        risk_level="low",
    )


def _verified_authority() -> tuple[
    Any, AuthorityEvidenceVerifierPolicy, AuthorityRevocationPolicy
]:
    """Create and cryptographically verify ephemeral AuthorityEvidence."""
    contract = _action_contract()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    issued_at = (NOW - timedelta(minutes=5)).isoformat()
    valid_until = (NOW + timedelta(minutes=30)).isoformat()
    evidence = AuthorityEvidence(
        authority_evidence_id="authority-decision-bind-poc",
        action_contract_id=contract.id,
        action_contract_version=contract.version,
        action_contract_hash=contract.deterministic_digest(),
        actor_identity=ACTOR,
        actor_role="synthetic-test-actor",
        authority_source_refs=["controlled-authority-fixture"],
        role_or_policy_basis=["synthetic-test-policy"],
        scope_grants=list(SCOPE),
        scope_limitations=[],
        validity_window={
            "issued_at": issued_at,
            "valid_from": issued_at,
            "valid_until": valid_until,
        },
        issued_at=issued_at,
        valid_from=issued_at,
        valid_until=valid_until,
        revalidated_at=NOW.isoformat(),
        policy_snapshot_id=POLICY_SNAPSHOT_ID,
        evidence_hash="",
        verification_result=VerificationResult.INDETERMINATE,
        failure_reasons=[],
        metadata={"synthetic_only": True},
    )
    claims = evidence.claims_dict()
    artifact: dict[str, Any] = {
        "artifact_type": "authority_evidence",
        "artifact_version": "v1",
        "claims": claims,
        "claims_hash": sha256_of_canonical_json(claims),
        "signer": {"key_id": "ephemeral-poc-key", "algorithm": "Ed25519"},
        "issuer_identity": "controlled-authority-fixture",
        "signed_at": NOW.isoformat(),
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(authority_signature_payload(artifact).encode("utf-8"))
    ).decode("ascii")
    verifier = TrustedEd25519AuthorityVerifier(
        trusted_public_keys={"ephemeral-poc-key": public_key},
        trusted_issuers={"ephemeral-poc-key": "controlled-authority-fixture"},
        verifier_id="decision-bind-poc-verifier",
    )
    signer_policy = AuthorityEvidenceSignerPolicy(
        policy_id="decision-bind-poc-signer-policy",
        allowed_key_ids=["ephemeral-poc-key"],
        allowed_algorithms=["Ed25519"],
        allowed_issuer_identities=["controlled-authority-fixture"],
    )
    verifier_policy = AuthorityEvidenceVerifierPolicy(
        approved_verifiers=[
            ApprovedAuthorityEvidenceVerifier(
                verifier_id=verifier.verifier_id,
                trust_level="production",
                verifier_key_id="ephemeral-poc-key",
                verifier_policy_id=verifier.verifier_policy_id,
                verifier_policy_hash=verifier.policy_hash(),
                signer_policy_id=signer_policy.policy_id,
                signer_policy_hash=signer_policy.deterministic_hash(),
            )
        ]
    )
    revocation_policy = AuthorityRevocationPolicy(
        max_age_seconds=60,
        allowed_source_identities=["controlled-revocation-fixture"],
    )
    proof = verify_authority_evidence_artifact_to_proof(
        artifact,
        action_contract=contract,
        actor_identity=ACTOR,
        requested_scope=list(SCOPE),
        policy_snapshot_id=POLICY_SNAPSHOT_ID,
        signature_verifier=verifier,
        signer_policy=signer_policy,
        verifier_policy=verifier_policy,
        revocation_checker=_NotRevoked(),
        revocation_policy=revocation_policy,
        now=NOW,
    )
    return proof, verifier_policy, revocation_policy


def _decide() -> tuple[dict[str, Any], bool]:
    """Cross the authenticated real HTTP route with controlled provider output."""
    from veritas_os.api import server
    from veritas_os.core import kernel as decision_kernel
    from veritas_os.core import llm_client

    transcript = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    calls = 0
    counters = {"calls": 0, "successful_calls": 0}

    def controlled_chat(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        nonlocal calls
        calls += 1
        return dict(transcript["response"])

    observed = _observed_kernel_decide(decision_kernel.decide, counters)
    with (
        patch.object(llm_client, "chat", controlled_chat),
        patch.object(decision_kernel, "decide", observed),
    ):
        with TestClient(server.app) as client:
            response = client.post(
                "/v1/decide",
                headers={"X-API-Key": os.environ["VERITAS_API_KEY"]},
                json=_request_fixture(),
            )
    response.raise_for_status()
    return response.json(), bool(
        calls and counters["calls"] and counters["successful_calls"]
    )


def run_proof(report_path: Path, *, invalid_authority: bool = False) -> int:
    """Run the integrated chain, gating Bind on strict runtime governance."""
    api_key = "poc-" + secrets.token_urlsafe(24)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    with tempfile.TemporaryDirectory(
        prefix="decision-bind-poc-", dir=REPO_ROOT / "runtime"
    ) as temporary:
        _configure_environment(Path(temporary), api_key, encryption_key)
        os.environ["VERITAS_POSTURE"] = "secure"
        if os.environ.get("VERITAS_POSTURE") != "secure":
            raise RuntimeError("integrated proof requires secure posture")

        response, pipeline_ok = _decide()
        raw_cda = response.get("canonical_decision_artifact")
        cda_verification = verify_canonical_decision_artifact(raw_cda)
        if not cda_verification.is_valid or cda_verification.artifact is None:
            raise RuntimeError("HTTP response canonical decision failed verification")
        cda: CanonicalDecisionArtifact = cda_verification.artifact
        promotion = (
            try_promote_verified_canonical_decision_candidate_to_execution_intent(
                _candidate(),
                canonical_decision_artifact=cda,
                policy_snapshot_id=POLICY_SNAPSHOT_ID,
                expected_state_fingerprint=sha256_of_canonical_json(SNAPSHOT),
                approval_context={"external_webhook_action_approved": True},
            )
        )
        if not promotion.promoted or promotion.execution_intent is None:
            raise RuntimeError("verified canonical decision was not promoted")
        intent = promotion.execution_intent
        lineage_ok = (
            intent.decision_id == cda.decision_id
            and intent.decision_hash == cda.decision_hash
            and intent.decision_ts == cda.decision_ts
            and intent.request_id == cda.request_id
        )
        proof, verifier_policy, revocation_policy = _verified_authority()
        runtime_result = RuntimeAuthorityValidator().validate(
            action_contract=_action_contract(),
            authority_evidence=None,
            verified_authority_evidence=None if invalid_authority else proof,
            authority_verifier_policy=verifier_policy,
            authority_revocation_policy=revocation_policy,
            requested_scope=list(SCOPE),
            required_evidence_metadata={},
            policy_snapshot_id=POLICY_SNAPSHOT_ID,
            actor_identity=ACTOR,
            human_approval_state={"approved": False},
            execution_intent_id=intent.execution_intent_id,
            bind_context_metadata={"proof": "decision-to-external-bind-poc"},
            now=NOW,
        )
        governance_commit = (
            runtime_result.status == "pass"
            and runtime_result.recommended_outcome == "commit"
        )
        bind_invoked = False
        receipt = None
        with LocalFixture() as fixture:
            if governance_commit:
                bind_invoked = True
                receipt = execute_bind_adjudication(
                    execution_intent=intent,
                    adapter=_adapter(fixture),
                    bind_ts=FIXED_TIMESTAMP,
                    append_trustlog=False,
                )
            action_posts = sum(
                item["method"] == "POST" and item["path"] == "/action"
                for item in fixture.state.requests
            )

        receipt_lineage = bool(
            receipt
            and receipt.decision_id == cda.decision_id
            and receipt.decision_hash == cda.decision_hash
            and receipt.execution_intent_id == intent.execution_intent_id
            and receipt.execution_intent_hash == hash_execution_intent(intent)
            and receipt.policy_snapshot_id == intent.policy_snapshot_id
        )
        expected = (
            not governance_commit
            and runtime_result.status == "fail"
            and runtime_result.recommended_outcome == "block"
            and not bind_invoked
            and action_posts == 0
            and receipt is None
            if invalid_authority
            else governance_commit
            and bind_invoked
            and action_posts == 1
            and receipt is not None
            and receipt.final_outcome is FinalOutcome.COMMITTED
            and receipt_lineage
        )
        report = {
            "format_version": 1,
            "proof_name": "VERITAS integrated Decision-to-Bind evidence PoC",
            "proof_scope": "network-real, effect-synthetic governance chain",
            "runtime_posture": "secure",
            "http_decide_status": "pass",
            "pipeline_kernel_status": "pass" if pipeline_ok else "fail",
            "canonical_decision_present": raw_cda is not None,
            "canonical_decision_verified": cda_verification.is_valid,
            "decision_id": cda.decision_id,
            "decision_hash": cda.decision_hash,
            "decision_ts": cda.decision_ts,
            "request_id": cda.request_id,
            "decision_candidate_source": "CONTROLLED_STRUCTURED_SYNTHETIC_CANDIDATE",
            "policy_snapshot_id": POLICY_SNAPSHOT_ID,
            "policy_snapshot_source": "CONTROLLED_SYNTHETIC_POLICY_FIXTURE",
            "execution_intent_created": True,
            "execution_intent_id": intent.execution_intent_id,
            "execution_intent_hash": hash_execution_intent(intent),
            "execution_intent_lineage_verified": lineage_ok,
            "authority_evidence_verified": not invalid_authority,
            "authority_verifier_policy_verified": not invalid_authority,
            "authority_revocation_verified": not invalid_authority,
            "human_approval_state": "NOT_REQUIRED",
            "runtime_authority_status": runtime_result.status,
            "runtime_authority_recommended_outcome": (
                runtime_result.recommended_outcome
            ),
            "bind_adjudication_invoked": bind_invoked,
            "bind_adjudication_call_count": int(bind_invoked),
            "webhook_bind_adapter_invoked": bind_invoked,
            "webhook_bind_adapter_call_count": int(bind_invoked),
            "external_post_occurred": action_posts > 0,
            "external_post_count": action_posts,
            "bind_receipt_created": receipt is not None,
            "bind_receipt_id": receipt.bind_receipt_id if receipt else None,
            "bind_final_outcome": (
                receipt.final_outcome.value if receipt else "NOT_INVOKED"
            ),
            "bind_reason_code": receipt.bind_reason_code if receipt else None,
            "decision_to_bind_receipt_lineage_verified": receipt_lineage,
            "real_bind_authorization_artifact_created": False,
            "authorization_consumption_exercised": False,
            "real_customer_endpoint_used": False,
            "production_credentials_used": False,
            "production_deployment_claimed": False,
            "production_worm_configured": False,
            "proof_non_claims": [
                "live LLM provider reliability",
                "production customer integration",
                "production credential handling",
                "Real Bind Authorization",
                "authorization consumption or atomic single-use enforcement",
                "production deployment",
                "regulatory approval or certification",
            ],
            "result": "pass" if expected and pipeline_ok and lineage_ok else "fail",
        }
        serialized = json.dumps(report, sort_keys=True, separators=(",", ":"))
        if api_key in serialized or encryption_key in serialized:
            raise RuntimeError("ephemeral secret leaked into proof report")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(serialized + "\n", encoding="utf-8")

    labels = {
        "HTTP_DECIDE": "PASS",
        "CANONICAL_DECISION": "VERIFIED",
        "DECISION_LINEAGE": "VERIFIED" if lineage_ok else "FAIL",
        "EXECUTION_INTENT": "CREATED",
        "EXECUTION_INTENT_LINEAGE": "VERIFIED" if lineage_ok else "FAIL",
        "RUNTIME_POSTURE": "secure",
        "AUTHORITY": "INVALID" if invalid_authority else "VERIFIED",
        "HUMAN_APPROVAL": "NOT_REQUIRED",
        "RUNTIME_AUTHORITY": (
            runtime_result.recommended_outcome.upper()
            if invalid_authority
            else runtime_result.status.upper()
        ),
        "BIND_ADJUDICATION": (
            "NOT_INVOKED" if not bind_invoked else receipt.final_outcome.value
        ),
        "WEBHOOK_BIND_ADAPTER": "INVOKED" if bind_invoked else "NOT_INVOKED",
        "EXTERNAL_POST_OCCURRED": str(action_posts > 0).upper(),
        "EXTERNAL_POST_COUNT": str(action_posts),
        "BIND_RECEIPT": "CREATED" if receipt else "NOT_CREATED",
        "DECISION_TO_RECEIPT_LINK": "VERIFIED" if receipt_lineage else "NOT_CREATED",
        "RESULT": "PASS" if report["result"] == "pass" else "FAIL",
    }
    for label, value in labels.items():
        print(f"{label:<30} {value}")
    return 0 if report["result"] == "pass" else 1


def main() -> int:
    """Parse proof mode and output location."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--negative-authority", action="store_true")
    args = parser.parse_args()
    return run_proof(args.report, invalid_authority=args.negative_authority)


if __name__ == "__main__":
    raise SystemExit(main())
