"""Regression tests for security findings F-06 / F-07.

F-06: public decision replay must never allow a caller to disable external API
mocking, including an auditor who is intentionally denied normal decide access.

F-07: trust-log read permission must not authorize trust feedback writes, and a
feedback write must be owned by the authenticated principal rather than a
caller-supplied user_id.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import auth, server


AUDITOR_KEY = "f06-auditor-key"
OPERATOR_KEY = "f07-operator-key"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("VERITAS_API_KEY", raising=False)
    monkeypatch.setenv(
        "VERITAS_API_KEYS",
        json.dumps(
            [
                {"key": AUDITOR_KEY, "role": "auditor"},
                {"key": OPERATOR_KEY, "role": "operator"},
            ]
        ),
    )
    server._rate_bucket.clear()
    yield TestClient(server.app)
    server._rate_bucket.clear()


def test_f06_auditor_cannot_disable_external_api_mocking(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakePipeline:
        async def replay_decision(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"match": True, "diff": {}}

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: FakePipeline())

    response = client.post(
        "/v1/decision/replay/decision-f06",
        headers={"X-API-Key": AUDITOR_KEY},
        params={"mock_external_apis": "false"},
    )

    assert response.status_code == 403
    assert response.json()["diff"]["error"] == "replay_external_apis_forbidden"
    assert calls == []


def test_f06_auditor_safe_replay_remains_mocked(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakePipeline:
        async def replay_decision(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"match": True, "diff": {}}

    monkeypatch.setattr(server, "get_decision_pipeline", lambda: FakePipeline())

    response = client.post(
        "/v1/decision/replay/decision-safe",
        headers={"X-API-Key": AUDITOR_KEY},
        params={"mock_external_apis": "true"},
    )

    assert response.status_code == 200
    assert response.json()["match"] is True
    assert calls == [
        {
            "decision_id": "decision-safe",
            "mock_external_apis": True,
        }
    ]


def test_f07_auditor_read_permission_cannot_write_trust_feedback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeValueCore:
        @staticmethod
        def append_trust_log(**kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(server, "get_value_core", lambda: FakeValueCore())

    response = client.post(
        "/v1/trust/feedback",
        headers={"X-API-Key": AUDITOR_KEY},
        json={
            "user_id": "victim-user",
            "score": 0.9,
            "note": "should not write",
        },
    )

    assert response.status_code == 403
    assert calls == []


def test_f07_operator_feedback_is_bound_to_authenticated_principal(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeValueCore:
        @staticmethod
        def append_trust_log(**kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(server, "get_value_core", lambda: FakeValueCore())

    response = client.post(
        "/v1/trust/feedback",
        headers={"X-API-Key": OPERATOR_KEY},
        json={
            "user_id": "victim-user",
            "score": 0.8,
            "note": "operator feedback",
            "source": "security-regression",
        },
    )

    expected_principal = auth._derive_api_user_id(OPERATOR_KEY)
    assert response.status_code == 200
    assert response.json()["user_id"] == expected_principal
    assert len(calls) == 1
    assert calls[0]["user_id"] == expected_principal
    assert calls[0]["user_id"] != "victim-user"
    assert calls[0]["extra"]["authenticated_principal_id"] == expected_principal
