"""Offline contract tests for Anthropic provider behavior in llm_client."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from veritas_os.core import llm_client
from veritas_os.core.llm_client import LLMError, SupportTier


@pytest.fixture(autouse=True)
def _reset_anthropic_test_state(monkeypatch: pytest.MonkeyPatch):
    """Isolate circuit state, pooled client, and Anthropic env across tests."""
    llm_client._circuit_state.clear()
    llm_client.close_pool()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield
    llm_client._circuit_state.clear()
    llm_client.close_pool()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _anthropic_success_response(text: str = "offline anthropic response") -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(
        status_code=200,
        json={
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 3},
        },
        request=request,
    )


def test_anthropic_support_tier_remains_planned() -> None:
    assert llm_client.PROVIDER_SUPPORT_TIER["anthropic"] == SupportTier.PLANNED
    assert llm_client.get_provider_support_tier("anthropic") == SupportTier.PLANNED
    assert llm_client.PROVIDER_SUPPORT_TIER["openai"] == SupportTier.PRODUCTION


def test_anthropic_endpoint_contract() -> None:
    assert llm_client._get_endpoint("anthropic") == "https://api.anthropic.com/v1/messages"


def test_anthropic_headers_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret")

    headers = llm_client._get_headers("anthropic")

    assert headers["x-api-key"] == "test-anthropic-secret"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["Content-Type"] == "application/json"
    assert "Authorization" not in headers


def test_anthropic_headers_missing_key_error_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(LLMError) as exc:
        llm_client._get_headers("anthropic")

    assert str(exc.value) == "ANTHROPIC_API_KEY not set"


def test_anthropic_model_allowlist_accepts_claude_models() -> None:
    assert llm_client._validate_model_name("anthropic", "claude-3-5-sonnet-latest") == (
        "claude-3-5-sonnet-latest"
    )
    assert llm_client._validate_model_name("anthropic", " claude-3-5-sonnet-latest ") == (
        "claude-3-5-sonnet-latest"
    )


@pytest.mark.parametrize(
    "model_name",
    [
        "gpt-4.1-mini",
        "gemini-1.5-pro",
        "../claude-3-5-sonnet",
        "claude-3-5-sonnet\nbad",
        "",
        "anthropic/claude-3-5-sonnet",
    ],
)
def test_anthropic_model_allowlist_rejects_non_claude_models(model_name: str) -> None:
    with pytest.raises(LLMError):
        llm_client._validate_model_name("anthropic", model_name)


def test_anthropic_format_request_contract() -> None:
    payload = llm_client._format_request(
        provider="anthropic",
        system_prompt="system rules",
        user_prompt="hello",
        model="claude-3-5-sonnet-latest",
        temperature=0.2,
        max_tokens=123,
        extra_messages=[
            {"role": "assistant", "content": "previous answer"},
            {"role": "user", "content": "follow-up"},
        ],
    )

    assert payload["model"] == "claude-3-5-sonnet-latest"
    assert payload["max_tokens"] == 123
    assert payload["temperature"] == 0.2
    assert payload["system"] == "system rules"
    assert payload["messages"][0] == {"role": "user", "content": "hello"}
    assert payload["messages"][1:] == [
        {"role": "assistant", "content": "previous answer"},
        {"role": "user", "content": "follow-up"},
    ]
    assert {"role": "system", "content": "system rules"} not in payload["messages"]
    assert "Authorization" not in payload
    assert "x-api-key" not in payload


def test_anthropic_format_request_normalizes_extra_messages() -> None:
    extras: list[Any] = [
        "skip-this-entry",
        {"content": 42},
        {"role": 123},
        {"role": "assistant", "content": "ok"},
    ] + [{"role": "assistant", "content": f"item-{idx}"} for idx in range(110)]

    payload = llm_client._format_request(
        provider="anthropic",
        system_prompt="sys",
        user_prompt="user",
        model="claude-3-5-sonnet-latest",
        temperature=0.1,
        max_tokens=50,
        extra_messages=extras,
    )

    messages = payload["messages"]
    assert messages[0] == {"role": "user", "content": "user"}
    assert messages[1] == {"role": "user", "content": "42"}
    assert messages[2] == {"role": "123", "content": ""}
    assert messages[3] == {"role": "assistant", "content": "ok"}
    # _format_request() truncates before normalization. The first 100 extras
    # include one non-dict entry that gets dropped, so the total is:
    # 1 user prompt + 99 normalized extras.
    assert len(messages) == 100


def test_anthropic_parse_response_extracts_text() -> None:
    parsed = llm_client._parse_response(
        "anthropic",
        {
            "content": [{"type": "text", "text": "hello from claude"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 4},
        },
    )

    assert parsed == "hello from claude"


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"content": [], "raw": "secret-token-should-not-leak"},
        {"content": [{"type": "text"}], "raw": "secret-token-should-not-leak"},
        {"unexpected": {"raw": "secret-token-should-not-leak"}},
    ],
)
def test_anthropic_parse_response_error_is_sanitized(bad_payload: dict[str, Any]) -> None:
    # Sentinel is intentionally embedded in malformed payloads to prove parse
    # errors do not echo raw provider content into surfaced error messages.
    with pytest.raises(LLMError) as exc:
        llm_client._parse_response("anthropic", bad_payload)

    message = str(exc.value)
    assert "LLM_PARSE_ERROR" in message
    assert "provider=anthropic" in message
    assert "cause=" in message
    assert "secret-token-should-not-leak" not in message


def test_anthropic_chat_emits_non_production_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret")
    monkeypatch.setattr(llm_client, "_http_post", lambda *args, **kwargs: _anthropic_success_response())

    with pytest.warns(UserWarning, match="planned") as warning_info:
        result = llm_client.chat(
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
            system_prompt="sys",
            user_prompt="hello",
        )

    warning_message = str(warning_info[0].message)
    assert "anthropic" in warning_message.lower()
    assert "test-anthropic-secret" not in warning_message
    assert result["provider"] == "anthropic"
    assert result["model"] == "claude-3-5-sonnet-latest"
    assert result["text"] == "offline anthropic response"


def test_anthropic_chat_uses_messages_endpoint_headers_and_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret")
    captured: dict[str, Any] = {}

    def _fake_http_post(url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        captured["timeout"] = kwargs.get("timeout")
        return _anthropic_success_response(text="captured response")

    monkeypatch.setattr(llm_client, "_http_post", _fake_http_post)

    with pytest.warns(UserWarning, match="planned"):
        result = llm_client.chat(
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
            system_prompt="system rules",
            user_prompt="hello",
        )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "test-anthropic-secret"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    system_payload = captured["json"]["system"]
    assert "system rules" in system_payload
    assert system_payload.endswith("system rules")
    assert captured["json"]["messages"][0] == {"role": "user", "content": "hello"}
    assert {"role": "system", "content": "system rules"} not in captured["json"]["messages"]
    assert all(message.get("role") != "system" for message in captured["json"]["messages"])
    assert captured["json"]["model"].startswith("claude-")
    assert result["text"] == "captured response"


def test_anthropic_chat_http_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret")

    def _fake_http_post(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=401,
            text='{"error":"raw-provider-error test-anthropic-secret"}',
            request=request,
        )

    monkeypatch.setattr(llm_client, "_http_post", _fake_http_post)

    with pytest.warns(UserWarning, match="planned"):
        with pytest.raises(LLMError) as exc:
            llm_client.chat(
                provider="anthropic",
                model="claude-3-5-sonnet-latest",
                system_prompt="sys",
                user_prompt="hello",
            )

    message = str(exc.value)
    assert "API error" in message
    assert "test-anthropic-secret" not in message
    assert "raw-provider-error" not in message
