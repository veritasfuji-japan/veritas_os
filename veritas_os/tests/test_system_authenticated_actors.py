"""Management mutations must attribute effects to authenticated API principals."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import auth, pipeline_orchestrator, routes_system, server
from veritas_os.core.eu_ai_act_oversight import SystemHaltController
from veritas_os.policy.bind_boundary_adapters import SystemResumeAdapter
from veritas_os.policy.bind_core import core as bind_core
from veritas_os.policy.governance_identity import compute_governance_digest
from veritas_os.security.hash import sha256_of_canonical_json


@pytest.fixture()
def management_state(monkeypatch):
    keys = ["management-actor-one", "management-actor-two"]
    monkeypatch.setenv("VERITAS_API_KEY", keys[0])
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([
        {"key": key, "role": "admin"} for key in keys
    ]))
    monkeypatch.setattr(server, "get_policy", lambda: {"version": "actor-fixture"})
    monkeypatch.setattr(routes_system, "_pending_system_resumes", {})
    monkeypatch.setattr(server, "SystemHaltController", SystemHaltController)
    for name, value in {
        "_halted": False, "_halted_by": None, "_halted_at": None,
        "_halt_reason": None, "_halt_id": None, "_history": [],
    }.items():
        monkeypatch.setattr(SystemHaltController, name, value)
    config = {"eu_ai_act_mode": False, "safety_threshold": 0.8}

    def update_config(**patch):
        config.update(patch)
        return dict(config)

    monkeypatch.setattr(routes_system, "get_runtime_config", lambda: dict(config))
    monkeypatch.setattr(routes_system, "update_runtime_config", update_config)
    intents = []
    monkeypatch.setattr(bind_core, "append_execution_intent_trustlog", intents.append)
    monkeypatch.setattr(bind_core, "append_bind_receipt_trustlog", lambda receipt: receipt)
    client = TestClient(server.app)
    try:
        yield client, config, intents
    finally:
        client.close()


def _request(client, operation: str, key: str):
    headers = {"X-API-Key": key, "X-Role": "claimed-other-person"}
    if operation == "config":
        return client.put(
            "/v1/compliance/config", headers=headers,
            json={"eu_ai_act_mode": True, "safety_threshold": 0.77},
        )
    return client.post(
        f"/v1/system/{operation}", headers=headers,
        json={"operator": "claimed-other-person", "reason": "test halt", "comment": "test resume"},
    )


@pytest.mark.parametrize("operation", ["halt", "resume", "config"])
@pytest.mark.parametrize("key", ["management-actor-one", "management-actor-two"])
def test_management_effect_actor_is_authenticated(management_state, operation, key):
    client, config, intents = management_state
    initial_halt = None
    if operation == "resume":
        initial_halt = SystemHaltController.halt(reason="test halt", operator="setup")
    response = _request(client, operation, key)
    assert response.status_code == 200
    assert response.json()["bind_outcome"] == "COMMITTED"
    expected = auth._derive_api_user_id(key)
    assert response.json()["bind_receipt"]["actor_identity"] == expected
    assert len(intents) == 1
    assert intents[0].actor_identity == expected
    if operation == "config":
        assert config == {"eu_ai_act_mode": True, "safety_threshold": 0.77}
    else:
        assert SystemHaltController.is_halted() is (operation == "halt")
        assert SystemHaltController._history[-1]["operator"] == expected
        action = {"operator": expected}
        action.update({"reason": "test halt"} if operation == "halt" else {"comment": "test resume"})
        if initial_halt is not None:
            action["halt_id"] = initial_halt["halt_id"]
        assert response.json()["bind_receipt"]["decision_hash"] == sha256_of_canonical_json(action)
        if operation == "halt":
            assert response.json()["halted_by"] == expected


@pytest.mark.parametrize("operation", ["halt", "resume", "config"])
def test_management_effect_refuses_missing_principal(
    monkeypatch, management_state, operation,
):
    client, config, intents = management_state
    SystemHaltController._halted = operation == "resume"
    before = SystemHaltController.status()
    monkeypatch.setattr(auth, "_bind_authenticated_principal", lambda request, key: None)
    response = _request(client, operation, "management-actor-one")
    assert response.status_code == 403
    assert intents == []
    assert config == {"eu_ai_act_mode": False, "safety_threshold": 0.8}
    assert SystemHaltController.status() == before
    assert SystemHaltController._history == []


@pytest.mark.parametrize("compliance_enabled", [False, True])
def test_http_halt_blocks_decide_until_resume(
    monkeypatch, management_state, compliance_enabled,
):
    """A committed halt must stop admission before loading the pipeline."""
    client, config, _ = management_state
    config["eu_ai_act_mode"] = compliance_enabled
    monkeypatch.setattr(pipeline_orchestrator, "get_runtime_config", lambda: dict(config))
    pipeline = SimpleNamespace(run_decide_pipeline=AsyncMock(return_value={
        "ok": True, "request_id": "halt-admission-test", "chosen": {},
    }))
    load_pipeline = Mock(return_value=pipeline)
    monkeypatch.setattr(server, "get_decision_pipeline", load_pipeline)
    monkeypatch.setattr(server, "_publish_event", lambda *args, **kwargs: None)
    headers = {"X-API-Key": "management-actor-one"}
    assert _request(client, "halt", headers["X-API-Key"]).json()["bind_outcome"] == "COMMITTED"

    for _ in range(2):
        response = client.post("/v1/decide", headers=headers, json={"query": "test"})
        assert response.status_code == 503
        assert response.json()["status"] == "HALTED"
        assert response.json()["decision_status"] == "rejected"
        assert response.json()["halt_status"]["halted"] is True
        assert response.json()["ok"] is False
    unauthenticated = client.post("/v1/decide", json={"query": "test"})
    assert unauthenticated.status_code == 401
    assert "halt_status" not in unauthenticated.json()
    load_pipeline.assert_not_called()
    pipeline.run_decide_pipeline.assert_not_awaited()

    assert _request(client, "resume", headers["X-API-Key"]).json()["bind_outcome"] == "COMMITTED"
    response = client.post("/v1/decide", headers=headers, json={"query": "test"})
    assert response.status_code == 200
    load_pipeline.assert_called_once()
    pipeline.run_decide_pipeline.assert_awaited_once()


def test_http_bind_denied_resume_keeps_decide_halted(monkeypatch, management_state):
    client, _, intents = management_state
    key = "management-actor-one"
    halt = _request(client, "halt", key)
    assert halt.status_code == 200
    assert halt.json()["bind_outcome"] == "COMMITTED"
    before = SystemHaltController.status()
    history_before = tuple(SystemHaltController._history)

    monkeypatch.setattr(
        SystemResumeAdapter, "validate_authority", lambda self, intent, snapshot: False
    )
    load_pipeline = Mock()
    monkeypatch.setattr(server, "get_decision_pipeline", load_pipeline)

    resume = _request(client, "resume", key)
    assert resume.status_code == 403
    body = resume.json()
    assert body["bind_outcome"] == "BLOCKED"
    assert body["bind_receipt"]["actor_identity"] == auth._derive_api_user_id(key)
    assert body["execution_intent_id"] == intents[-1].execution_intent_id
    assert SystemHaltController.status() == before
    assert tuple(SystemHaltController._history) == history_before

    decide = client.post(
        "/v1/decide", headers={"X-API-Key": key}, json={"query": "test"}
    )
    assert decide.status_code == 503
    assert decide.json()["status"] == "HALTED"
    load_pipeline.assert_not_called()


def test_http_resume_without_active_halt_refuses_state_change(monkeypatch, management_state):
    client, _, intents = management_state
    resume = Mock(wraps=SystemHaltController.resume)
    conditional_resume = Mock(wraps=SystemHaltController.resume_if_halt_matches)
    monkeypatch.setattr(SystemHaltController, "resume", resume)
    monkeypatch.setattr(SystemHaltController, "resume_if_halt_matches", conditional_resume)

    response = _request(client, "resume", "management-actor-one")

    assert response.status_code == 409
    assert response.json()["error"] == "No active halt to resume"
    resume.assert_not_called()
    conditional_resume.assert_not_called()
    assert not intents
    assert not SystemHaltController._history


@pytest.mark.parametrize("replacement_before_clear", [True, False])
def test_http_resume_preserves_replacement_halt(
    monkeypatch, management_state, replacement_before_clear,
):
    client, _, _ = management_state
    key = "management-actor-one"
    halt = _request(client, "halt", key)
    assert halt.status_code == 200
    first_halt = SystemHaltController.status()["halt_id"]
    assert first_halt
    monkeypatch.setattr(
        server, "get_policy",
        lambda: {"version": "actor-fixture", "bind_adjudication": {"rollback_on_apply_failure": True}},
    )

    conditional_resume = SystemHaltController.resume_if_halt_matches

    def replace_halt_during_resume(**kwargs):
        if replacement_before_clear:
            SystemHaltController.halt(reason="replacement", operator="op")
        result = conditional_resume(**kwargs)
        if not replacement_before_clear:
            SystemHaltController.halt(reason="replacement", operator="op")
        return result

    monkeypatch.setattr(
        SystemHaltController, "resume_if_halt_matches", replace_halt_during_resume
    )
    response = _request(client, "resume", key)
    assert response.status_code == (403 if replacement_before_clear else 200)
    if replacement_before_clear:
        assert response.json()["bind_outcome"] == "BLOCKED"
        assert response.json()["bind_reason_code"] == "state_conflict"
    else:
        assert response.json()["bind_outcome"] == "COMMITTED"
    status = SystemHaltController.status()
    assert status["halted"] is True
    assert status["halt_id"] != first_halt
    resumes = [
        event["halt_id"] for event in SystemHaltController._history
        if event["action"] == "resume"
    ]
    assert resumes == ([] if replacement_before_clear else [first_halt])


@pytest.mark.parametrize("change", ["halt", "policy", "deployment"])
def test_resume_preparation_refreshes_stale_context(monkeypatch, management_state, change):
    client, _, intents = management_state
    monkeypatch.setenv("VERITAS_DEPLOYMENT_ID", "fixture-deployment")
    halt = SystemHaltController.halt(reason="test halt", operator="setup")
    headers = {"X-API-Key": "management-actor-one"}
    path = "/v1/system/resume/prepare"
    first = client.post(path, headers=headers)
    assert first.status_code == 200
    assert client.post(path, headers=headers).json() == first.json()
    if change == "halt":
        halt = SystemHaltController.halt(reason="replacement halt", operator="setup")
    elif change == "policy":
        monkeypatch.setattr(server, "get_policy", lambda: {"version": "updated"})
    else:
        monkeypatch.setenv("VERITAS_DEPLOYMENT_ID", "updated-deployment")
    second = client.post(path, headers=headers)
    assert second.status_code == 200
    assert second.json()["request_id"] != first.json()["request_id"]
    assert second.json()["execution_intent_id"] != first.json()["execution_intent_id"]
    assert second.json()["halt_id"] == halt["halt_id"]
    assert list(routes_system._pending_system_resumes) == [second.json()["request_id"]]
    assert SystemHaltController.is_halted()
    assert not intents


def test_resume_preparation_requires_active_halt_and_deployment(monkeypatch, management_state):
    client, _, _ = management_state
    monkeypatch.delenv("VERITAS_DEPLOYMENT_ID", raising=False)
    headers = {"X-API-Key": "management-actor-one"}
    path = "/v1/system/resume/prepare"
    assert client.post(path, headers=headers).status_code == 409
    SystemHaltController.halt(reason="test halt", operator="setup")
    assert client.post(path, headers=headers).status_code == 503
    assert SystemHaltController.is_halted()
    assert not routes_system._pending_system_resumes


def test_resume_preparation_refuses_unavailable_policy(monkeypatch, management_state):
    client, _, intents = management_state
    monkeypatch.setenv("VERITAS_DEPLOYMENT_ID", "fixture-deployment")
    halt = SystemHaltController.halt(reason="test halt", operator="setup")
    monkeypatch.setattr(server, "get_policy", Mock(side_effect=RuntimeError("policy unavailable")))
    response = client.post("/v1/system/resume/prepare", headers={"X-API-Key": "management-actor-one"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Resume preparation unavailable"
    assert SystemHaltController.status()["halt_id"] == halt["halt_id"]
    assert SystemHaltController.is_halted()
    assert not routes_system._pending_system_resumes
    assert not intents


def test_strict_lifespan_requires_resume_after_each_start(monkeypatch, management_state):
    """Each strict API lifecycle refuses decisions until an authenticated resume."""
    from veritas_os.api import governance, lifespan
    from veritas_os.api import middleware
    from veritas_os.core import posture

    client, _, intents = management_state
    for module in (server, middleware):
        monkeypatch.setattr(module, "_shutting_down", False)
        monkeypatch.setattr(module, "_inflight_count", 0)
    for name in ("memory_store", "trust_log_store"):
        monkeypatch.setattr(server.app.state, name, None, raising=False)
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_DEPLOYMENT_ID", "fixture-deployment")
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([
        {"key": "management-actor-one", "role": "admin"},
        {"key": "startup-operator", "role": "operator"},
    ]))
    monkeypatch.setattr(
        posture, "init_posture",
        lambda **kwargs: posture.PostureDefaults(posture.PostureLevel.DEV),
    )
    monkeypatch.setattr(posture, "set_active_posture", lambda defaults: None)
    for name in ("validate_backend_config", "validate_trustlog_secure_defaults"):
        monkeypatch.setattr(lifespan, name, lambda: None)
    for name in ("create_memory_store", "create_trust_log_store"):
        monkeypatch.setattr(lifespan, name, lambda: object())
    monkeypatch.setattr(governance, "configure_governance_repository_from_env", lambda: None)
    for name in (
        "_run_startup_config_validation", "_check_runtime_feature_health",
        "_check_multiworker_auth_store", "_start_nonce_cleanup_scheduler",
        "_start_rate_cleanup_scheduler", "_stop_nonce_cleanup_scheduler",
        "_stop_rate_cleanup_scheduler", "_close_llm_pool",
    ):
        monkeypatch.setattr(server, name, lambda: None)
    pipeline = SimpleNamespace(run_decide_pipeline=AsyncMock(return_value={
        "ok": True, "request_id": "strict-start-test", "chosen": {},
    }))
    load_pipeline = Mock(return_value=pipeline)
    monkeypatch.setattr(server, "get_decision_pipeline", load_pipeline)
    monkeypatch.setattr(server, "_publish_event", lambda *args, **kwargs: None)
    headers = {"X-API-Key": "management-actor-one"}
    for _ in range(2):
        with client:
            load_pipeline.reset_mock()
            response = client.post("/v1/decide", headers=headers, json={"query": "test"})
            assert response.status_code == 503
            assert response.json()["status"] == "HALTED"
            load_pipeline.assert_not_called()
            denied = _request(client, "resume", "startup-operator")
            assert denied.status_code == 403
            assert SystemHaltController.is_halted() is True
            path = "/v1/system/resume/prepare"
            denied = client.post(path, headers={"X-API-Key": "startup-operator"})
            assert denied.status_code == 403
            active_halt = SystemHaltController.status()["halt_id"]
            count = len(intents)
            prepared = client.post(path, headers=headers, json={"operator": "other"})
            assert prepared.status_code == 200
            body = prepared.json()
            assert body["request_id"]
            assert body["execution_intent_id"]
            assert body["action"] == "system_resume"
            assert body["halt_id"] == active_halt
            assert body["deployment_id"] == "fixture-deployment"
            assert body["execution_principal"] == auth._derive_api_user_id(headers["X-API-Key"])
            assert body["policy_snapshot_digest"] == compute_governance_digest(server.get_policy())
            assert len(intents) == count
            response = client.post("/v1/decide", headers=headers, json={"query": "test"})
            assert response.status_code == 503
            assert response.json()["status"] == "HALTED"
            load_pipeline.assert_not_called()
            assert _request(client, "resume", headers["X-API-Key"]).json()["bind_outcome"] == "COMMITTED"
            response = client.post("/v1/decide", headers=headers, json={"query": "test"})
            assert response.status_code == 200
            load_pipeline.assert_called_once()


def test_independent_resume_approval_issues_bound_receipt(monkeypatch, tmp_path, management_state):
    import base64
    from datetime import datetime, timedelta

    from veritas_os.governance.human_approval_receipt import (
        HumanApprovalSignerPolicy, verify_human_approval_receipt_artifact_to_proof,
    )
    from veritas_os.governance.human_approval_receipt_signing import TrustedEd25519HumanApprovalVerifier
    from veritas_os.security.hash import sha256_hex
    from veritas_os.security.signing import store_keypair

    client, _, intents = management_state
    executor = {"X-API-Key": "management-actor-one"}
    reviewer = {"X-API-Key": "management-actor-two"}
    identity = auth._derive_api_user_id(reviewer["X-API-Key"])
    monkeypatch.setenv("VERITAS_DEPLOYMENT_ID", "fixture-deployment")
    monkeypatch.setenv("VERITAS_SYSTEM_RESUME_APPROVER_ID", identity)
    key = tmp_path / "approval.key"
    pub = tmp_path / "approval.pub"
    monkeypatch.setenv("VERITAS_SYSTEM_RESUME_SIGNING_KEY_FILE", str(key))
    halt = SystemHaltController.halt(reason="test", operator="setup")
    prepared = client.post("/v1/system/resume/prepare", headers=executor).json()
    review = "/v1/system/resume/requests/" + prepared["request_id"]
    assert client.get(review, headers=executor).status_code == 403
    details = client.get(review, headers=reviewer).json()
    assert details["preparation"] == prepared
    decision = {"decision": "approve", "context_hash": details["context_hash"]}
    approve = review + "/approve"
    assert client.post(approve, headers=executor, json=decision).status_code == 403
    monkeypatch.setenv("VERITAS_SYSTEM_RESUME_APPROVER_ID", prepared["execution_principal"])
    assert client.post(approve, headers=executor, json=decision).status_code == 403
    monkeypatch.setenv("VERITAS_SYSTEM_RESUME_APPROVER_ID", identity)
    assert client.post(approve, headers=reviewer, json={**decision, "context_hash": "0"*64}).status_code == 409
    assert client.post(approve, headers=reviewer, json=decision).status_code == 503
    with monkeypatch.context() as scoped:
        scoped.setattr(server, "get_policy", lambda: {"approval_workflow": {"approver_identities": ["other"]}})
        assert client.post(approve, headers=reviewer, json=decision).status_code == 403
    store_keypair(key, pub)
    response = client.post(approve, headers=reviewer, json=decision)
    assert response.status_code == 200
    artifact = response.json()
    assert client.post(approve, headers=reviewer, json=decision).json() == artifact
    public_key = base64.urlsafe_b64decode(pub.read_bytes())
    kid = sha256_hex(public_key)
    role = "system_resume_approver"
    verifier = TrustedEd25519HumanApprovalVerifier({kid: public_key}, {kid: identity}, {kid: role}, "fixture")
    policy = HumanApprovalSignerPolicy("resume-policy", [kid], ["Ed25519"], [role], [identity], ["system_resume"])
    proof = verify_human_approval_receipt_artifact_to_proof(
        artifact, verifier.verify, signer_policy=policy, require_structured_signature_result=True,
        requested_scope=["system_resume"], action_class="system_resume",
        policy_snapshot_id=prepared["policy_snapshot_digest"],
    )
    assert proof.receipt.metadata["system_resume"] == prepared
    assert proof.receipt.approver_identity == identity
    assert proof.receipt.execution_intent_id == prepared["execution_intent_id"]
    assert proof.receipt.bind_context_hash == sha256_of_canonical_json(prepared)
    assert datetime.fromisoformat(proof.receipt.expires_at) - datetime.fromisoformat(proof.receipt.approved_at) == timedelta(minutes=5)
    assert SystemHaltController.status()["halt_id"] == halt["halt_id"]
    assert not intents
    response = client.post("/v1/decide", headers=executor, json={"query": "test"})
    assert response.status_code == 503 and response.json()["status"] == "HALTED"
    with monkeypatch.context() as scoped:
        clock = Mock(wraps=datetime)
        clock.now.return_value = datetime.fromisoformat(proof.receipt.expires_at)
        scoped.setattr(routes_system, "datetime", clock)
        assert client.post(approve, headers=reviewer, json=decision).status_code == 409
        renewed = client.post("/v1/system/resume/prepare", headers=executor).json()
        assert renewed["request_id"] != prepared["request_id"]
    current_review = "/v1/system/resume/requests/" + renewed["request_id"]
    current_hash = client.get(current_review, headers=reviewer).json()["context_hash"]
    SystemHaltController.halt(reason="replacement", operator="setup")
    stale = client.post(current_review + "/approve", headers=reviewer,
                        json={"decision": "approve", "context_hash": current_hash})
    assert stale.status_code == 409


@pytest.mark.parametrize("retry_approval_first", [True, False])
def test_resume_key_rotation_requires_new_review(monkeypatch, tmp_path, management_state, retry_approval_first):
    from veritas_os.security.signing import store_keypair

    client, _, _ = management_state
    executor = {"X-API-Key": "management-actor-one"}
    reviewer = {"X-API-Key": "management-actor-two"}
    key, pub = store_keypair(tmp_path / "approval.key", tmp_path / "approval.pub")
    monkeypatch.setenv("VERITAS_SYSTEM_RESUME_SIGNING_KEY_FILE", str(key))
    monkeypatch.setenv("VERITAS_DEPLOYMENT_ID", "fixture-deployment")
    monkeypatch.setenv("VERITAS_SYSTEM_RESUME_APPROVER_ID", auth._derive_api_user_id(reviewer["X-API-Key"]))
    SystemHaltController.halt(reason="test", operator="setup")
    prepare = "/v1/system/resume/prepare"
    requests = "/v1/system/resume/requests/"
    original = client.post(prepare, headers=executor).json()
    review = requests + original["request_id"]
    decision = {"decision": "approve", "context_hash": client.get(review, headers=reviewer).json()["context_hash"]}
    approve = review + "/approve"
    old = client.post(approve, headers=reviewer, json=decision).json()
    key.chmod(0o620)
    assert client.post(approve, headers=reviewer, json=decision).status_code == 503
    key.chmod(0o600)
    store_keypair(key, pub)
    if retry_approval_first:
        assert client.post(approve, headers=reviewer, json=decision).status_code == 409
    fresh = client.post(prepare, headers=executor).json()
    assert fresh["request_id"] != original["request_id"]
    assert client.post(approve, headers=reviewer, json=decision).status_code == 404
    review = requests + fresh["request_id"]
    approve = review + "/approve"
    assert client.post(approve, headers=reviewer, json=decision).status_code == 409
    decision["context_hash"] = client.get(review, headers=reviewer).json()["context_hash"]
    new = client.post(approve, headers=reviewer, json=decision).json()
    assert new["signer"]["key_id"] != old["signer"]["key_id"]
    assert client.post(approve, headers=reviewer, json=decision).json() == new
