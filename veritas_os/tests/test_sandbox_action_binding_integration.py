"""Signed native authorization must contain the action reference before issuance."""

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pytest

from veritas_os.policy import sandbox_action_binding as binding
from veritas_os.policy.canonical_verified_decision_promotion import (
    build_canonical_verified_decision_promotion_packet,
)
from veritas_os.tests.helpers.native_approval_source import build_native_authority_source
from veritas_os.tests import test_canonical_promotion_live_adapter_dry_run_endpoint_allowlist as endpoints
from veritas_os.tests import test_canonical_promotion_live_adapter_dry_run_credential_authorization as credentials
from veritas_os.tests.test_native_bind_authorization import _setup
from veritas_os.tests.test_sandbox_action_binding import PAYLOAD, build, contract, deployment

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def issued(tmp_path_factory):
    """Capture the real API and sign synthetic fixtures; never mock verifiers."""
    output = tmp_path_factory.mktemp("sandbox-native") / "capture.json"
    config = deployment()
    overrides = {
        "intended_action": binding.ACTION,
        "target_system": config.target_system,
        "target_resource": config.endpoint_url,
        "evidence_refs": [build().reference],
    }
    code = (
        "import json,sys; from pathlib import Path; "
        "from veritas_os.tests.helpers.live_decision_capture import capture; "
        "capture(Path(sys.argv[1]), candidate_overrides=json.loads(sys.argv[2]))"
    )
    subprocess.run(
        [sys.executable, "-c", code, str(output), json.dumps(overrides)],
        cwd=Path(__file__).resolve().parents[2], check=True, timeout=180,
        capture_output=True, text=True,
    )
    captured = json.loads(output.read_text())
    assert captured["pipeline_ok"]
    now = datetime.fromisoformat(captured["observed_at"])
    promotion = build_canonical_verified_decision_promotion_packet(
        captured["canonical_decision_artifact"], captured["candidate"],
        promoted_at=now, ttl_seconds=300,
        expected_state_fingerprint="synthetic:sandbox:empty",
    )
    original = endpoints._candidate
    original_reference = credentials._reference
    with pytest.MonkeyPatch.context() as patch:
        # Change only fixture metadata; all source builders/verifiers are real.
        patch.setattr(endpoints, "_candidate", lambda **kw: original(
            **kw, endpoint_host="sandbox.example.invalid", endpoint_path_prefix="/v1/events",
        ))
        patch.setattr(credentials, "_reference", lambda **kw: original_reference(
            **kw, credential_scope=config.credential_scope,
            credential_environment=config.credential_environment,
        ))
        source = build_native_authority_source(promotion, now)
    artifact, inputs, *_ = _setup(source, contract(), now)
    return artifact, inputs


def verify(issued, payload=None, config=None):
    artifact, inputs = issued
    return binding.verify_sandbox_action_binding(
        artifact, json.dumps(PAYLOAD if payload is None else payload),
        deployment=deployment() if config is None else config, **inputs,
    )


def test_real_native_signature_and_source_accept_original_request(issued):
    artifact, _ = issued
    verified = verify(issued)
    assert verified.binding == build()
    assert verified.idempotency_key == artifact.idempotency_key
    assert verified.authorization_hash == artifact.authorization_hash
    assert not artifact.credential_material_accessed and not artifact.bind_invoked


@pytest.mark.parametrize("field,value", [
    ("message", "changed"),
    ("event_id", "12345678-1234-4234-8234-123456789abd"),
])
def test_recomputed_payload_reference_cannot_rebind_signed_authorization(issued, field, value):
    with pytest.raises(binding.SandboxActionBindingError, match="AUTHORIZATION_BINDING"):
        verify(issued, {**PAYLOAD, field: value})


@pytest.mark.parametrize("field,value", [
    ("endpoint_url", "https://another.example.invalid/v1/events"),
    ("credential_version", "2"),
    ("credential_reference_id", "credential:attacker"),
    ("credential_scope", "admin"),
    ("target_system", "another-system"),
])
def test_deployment_changes_cannot_rebind_existing_authorization(issued, field, value):
    with pytest.raises(binding.SandboxActionBindingError):
        verify(issued, config=replace(deployment(), **{field: value}))


def test_adding_reference_after_issuance_is_rejected(issued):
    artifact, inputs = issued
    raw = artifact.model_dump(mode="json")
    raw["execution_intent"]["evidence_refs"].append(build().reference)
    with pytest.raises(ValueError):
        verify((raw, inputs))


def test_corrupted_native_signature_is_rejected(issued):
    artifact, inputs = issued
    raw = artifact.model_dump(mode="json")
    raw["authorization_signature"] = "A" * 88
    with pytest.raises(ValueError):
        verify((raw, inputs))


def test_current_metadata_cannot_be_replaced_from_embedded_snapshot(issued):
    artifact, inputs = issued
    original = inputs["source_inputs"]
    changed = replace(original, current_credential_reference={
        **original.current_credential_reference, "credential_scope": "admin",
    })
    with pytest.raises(ValueError):
        verify((artifact, {**inputs, "source_inputs": changed}))


def test_same_id_version_contract_change_rejected(issued):
    artifact, inputs = issued
    gov = inputs["governance_inputs"]
    changed = replace(gov.action_contract, human_approval_rules={"required": True})
    with pytest.raises(ValueError):
        verify((artifact, {**inputs, "governance_inputs": replace(gov, action_contract=changed)}))
