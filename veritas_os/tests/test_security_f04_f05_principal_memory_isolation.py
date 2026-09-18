"""Regression tests for security findings F-04 / F-05.

F-04: authenticated /v1/decide memory ownership must come from the trusted
principal rather than request body/context user_id.

F-05: memory writes must not allow caller-controlled meta.user_id to redirect
persistence into another principal's namespace.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from veritas_os.api import auth, server
from veritas_os.api.rbac import Permission
from veritas_os.core.memory import memory_search_helpers
from veritas_os.core.memory.memory_store_helpers import put_episode_record
from veritas_os.core.pipeline.pipeline_inputs import normalize_pipeline_inputs
from veritas_os.core.pipeline.pipeline_retrieval import stage_memory_retrieval
from veritas_os.core.pipeline.pipeline_types import PipelineContext


KEY_A = "f04-operator-a"
KEY_B = "f04-operator-b"


def _multi_key_config() -> str:
    return json.dumps(
        [
            {"key": KEY_A, "role": "operator"},
            {"key": KEY_B, "role": "operator"},
        ]
    )


def _principal(key: str) -> str:
    return auth._derive_api_user_id(key)


def test_f04_permission_dependency_binds_authenticated_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_API_KEYS", _multi_key_config())
    request = SimpleNamespace(
        state=SimpleNamespace(),
        url=SimpleNamespace(path="/v1/decide"),
        method="POST",
    )

    checker = auth.require_permission(Permission.decide)
    assert checker(request=request, x_api_key=KEY_B) is True

    assert request.state.authenticated_principal_id == _principal(KEY_B)
    assert request.state.user_id == _principal(KEY_B)


def test_f04_pipeline_request_user_id_cannot_replace_authenticated_principal() -> None:
    principal_a = _principal(KEY_A)
    principal_b = _principal(KEY_B)
    request = SimpleNamespace(
        state=SimpleNamespace(authenticated_principal_id=principal_b),
        query_params={},
    )

    ctx = normalize_pipeline_inputs(
        {
            "query": "find my private memory",
            "user_id": principal_a,
            "context": {"user_id": principal_a},
        },
        request,
    )

    assert ctx.user_id == principal_b
    assert ctx.context["user_id"] == principal_b
    assert ctx.body["context"]["user_id"] == principal_b


def test_f04_pipeline_retrieval_rejects_cross_principal_and_unowned_hits() -> None:
    principal_a = _principal(KEY_A)
    principal_b = _principal(KEY_B)
    ctx = PipelineContext(
        query="private note",
        context={},
        body={},
        user_id=principal_b,
        response_extras={
            "metrics": {
                "mem_hits": 0,
                "memory_evidence_count": 0,
                "stage_latency": {"retrieval": 0},
            },
            "env_tools": {},
        },
    )

    def fake_search(_store: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        # Deliberately ignore the supplied user_id to model a buggy / legacy
        # backend. The pipeline boundary must still reject foreign evidence.
        return [
            {
                "id": "foreign",
                "text": "A private secret",
                "score": 0.99,
                "meta": {"user_id": principal_a, "kind": "episodic"},
            },
            {
                "id": "unowned",
                "text": "legacy unowned secret",
                "score": 0.98,
                "meta": {"kind": "episodic"},
            },
            {
                "id": "mine",
                "text": "B private note",
                "score": 0.97,
                "meta": {"user_id": principal_b, "kind": "episodic"},
            },
        ]

    stage_memory_retrieval(
        ctx,
        _get_memory_store=lambda: object(),
        _memory_search=fake_search,
        _memory_put=lambda *_args, **_kwargs: None,
        _memory_add_usage=lambda *_args, **_kwargs: None,
        _flatten_memory_hits=lambda src, **_kwargs: list(src or []),
        _warn=lambda _message: None,
        utc_now_iso_z=lambda: "2026-09-19T00:00:00Z",
    )

    assert [item["id"] for item in ctx.retrieved] == ["mine"]
    assert len(ctx.evidence) == 1
    assert "B private note" in ctx.evidence[0]["snippet"]
    assert "A private secret" not in str(ctx.evidence)
    assert "legacy unowned secret" not in str(ctx.evidence)


def test_f04_vector_search_does_not_restore_foreign_hits_after_empty_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veritas_os.core import memory as memory_mod

    principal_a = _principal(KEY_A)
    principal_b = _principal(KEY_B)

    class FakeVector:
        def search(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "id": "foreign-vector",
                    "text": "A vector secret",
                    "score": 1.0,
                    "meta": {"user_id": principal_a},
                }
            ]

    class FakeKvs:
        def search(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
            assert kwargs["user_id"] == principal_b
            return {
                "episodic": [
                    {
                        "id": "mine-kvs",
                        "text": "B scoped result",
                        "score": 0.9,
                        "meta": {"user_id": principal_b},
                    }
                ]
            }

    monkeypatch.setattr(memory_mod, "_get_mem_vec", lambda: FakeVector())
    monkeypatch.setattr(memory_mod, "MEM", FakeKvs())

    hits = memory_mod.search("secret", user_id=principal_b)

    assert [hit["id"] for hit in hits] == ["mine-kvs"]
    assert all(
        (hit.get("meta") or {}).get("user_id") == principal_b
        for hit in hits
    )


def test_strict_owner_filter_rejects_unowned_and_foreign_hits() -> None:
    hits = [
        {"text": "shared", "meta": {}},
        {"text": "mine", "meta": {"user_id": "u1"}},
        {"text": "other", "meta": {"user_id": "u2"}},
    ]

    assert memory_search_helpers.filter_hits_for_user(
        hits,
        "u1",
        include_unowned=False,
    ) == [{"text": "mine", "meta": {"user_id": "u1"}}]


def test_f05_memory_put_overwrites_meta_user_id_with_authenticated_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_API_KEYS", _multi_key_config())
    captured: dict[str, Any] = {}

    class CaptureStore:
        def put(self, kind: str, item: dict[str, Any]) -> str:
            captured["kind"] = kind
            captured["item"] = item
            return "record-1"

    monkeypatch.setattr(server, "get_memory_store", lambda: CaptureStore())
    client = TestClient(server.app)

    response = client.post(
        "/v1/memory/put",
        headers={"X-API-Key": KEY_B},
        json={
            "text": "B-owned record",
            "kind": "semantic",
            "user_id": _principal(KEY_A),
            "meta": {"user_id": _principal(KEY_A), "source": "security-test"},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["item"]["meta"]["user_id"] == _principal(KEY_B)
    assert captured["item"]["meta"]["source"] == "security-test"


def test_f05_core_memory_add_explicit_owner_overrides_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veritas_os.core import memory as memory_mod

    captured: dict[str, Any] = {}

    class FakeMem:
        def put(self, user_id: str, key: str, value: dict[str, Any]) -> bool:
            captured["user_id"] = user_id
            captured["value"] = value
            return True

    monkeypatch.setattr(memory_mod, "MEM", FakeMem())
    monkeypatch.setattr(memory_mod, "_get_mem_vec", lambda: None)

    result = memory_mod.add(
        user_id="owner-b",
        text="owned note",
        meta={"user_id": "owner-a"},
    )

    assert captured["user_id"] == "owner-b"
    assert captured["value"]["meta"]["user_id"] == "owner-b"
    assert result["meta"]["user_id"] == "owner-b"


def test_f05_put_episode_explicit_owner_overrides_metadata() -> None:
    captured: dict[str, Any] = {}

    class CaptureStore:
        def put(self, user_id: str, key: str, record: dict[str, Any]) -> bool:
            captured["user_id"] = user_id
            captured["record"] = record
            return True

    put_episode_record(
        store=CaptureStore(),
        text="episode",
        meta={"user_id": "owner-a"},
        user_id="owner-b",
        time_module=SimpleNamespace(time=lambda: 1),
    )

    assert captured["user_id"] == "owner-b"
    assert captured["record"]["meta"]["user_id"] == "owner-b"
