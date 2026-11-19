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
from veritas_os.security.hash import sha256_of_canonical_json


@pytest.fixture()
def management_state(monkeypatch):
    keys = ["management-actor-one", "management-actor-two"]
    monkeypatch.setenv("VERITAS_API_KEY", keys[0])
    monkeypatch.setenv("VERITAS_API_KEYS", json.dumps([
        {"key": key, "role": "admin"} for key in keys
    ]))
    monkeypatch.setattr(server, "get_policy", lambda: {"version": "actor-fixture"})
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


def test_strict_lifespan_requires_resume_after_each_start(monkeypatch, management_state):
    """Each strict API lifecycle refuses decisions until an authenticated resume."""
    from veritas_os.api import governance, lifespan
    from veritas_os.api import middleware
    from veritas_os.core import posture

    client, _, _ = management_state
    for module in (server, middleware):
        monkeypatch.setattr(module, "_shutting_down", False)
        monkeypatch.setattr(module, "_inflight_count", 0)
    for name in ("memory_store", "trust_log_store"):
        monkeypatch.setattr(server.app.state, name, None, raising=False)
    monkeypatch.setenv("VERITAS_ENV", "production")
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
            assert _request(client, "resume", headers["X-API-Key"]).json()["bind_outcome"] == "COMMITTED"
            response = client.post("/v1/decide", headers=headers, json={"query": "test"})
            assert response.status_code == 200
            load_pipeline.assert_called_once()
