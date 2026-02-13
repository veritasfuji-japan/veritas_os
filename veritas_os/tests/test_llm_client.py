# tests/test_llm_client.py
import importlib
from unittest.mock import MagicMock

import pytest
import requests

from veritas_os.core import llm_client
from veritas_os.core.llm_client import (
    LLMProvider,
    LLMError,
    _format_request,
    _parse_response,
    _get_api_key,
    _get_endpoint,
    _get_headers,
)


# ------------------------------------------------------------
# ヘルパークラス
# ------------------------------------------------------------

class _DummyResponse:
    def __init__(self, status_code: int, data: dict, text: str = ""):
        self.status_code = status_code
        self._data = data
        self.text = text or ""
        self.headers = {}
        self.content = (text or "").encode("utf-8")

    def json(self):
        return self._data


# ------------------------------------------------------------
# _get_api_key / _get_endpoint のテスト
# ------------------------------------------------------------

def test_get_api_key_openai_and_fallback(monkeypatch):
    # OPENAI_API_KEY 優先
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("OPEN_API_KEY", raising=False)
    assert _get_api_key(LLMProvider.OPENAI.value) == "sk-openai"

    # OPEN_API_KEY フォールバック
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_API_KEY", "sk-openai-fallback")
    assert _get_api_key(LLMProvider.OPENAI.value) == "sk-openai-fallback"


def test_get_api_key_other_providers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
    monkeypatch.setenv("GOOGLE_API_KEY", "gk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "ork-test")

    assert _get_api_key(LLMProvider.ANTHROPIC.value) == "ak-test"
    assert _get_api_key(LLMProvider.GOOGLE.value) == "gk-test"
    assert _get_api_key(LLMProvider.OPENROUTER.value) == "ork-test"
    # Ollama は None
    assert _get_api_key(LLMProvider.OLLAMA.value) is None


def test_get_endpoint_each_provider():
    assert _get_endpoint(LLMProvider.OPENAI.value) == "https://api.openai.com/v1/chat/completions"
    assert _get_endpoint(LLMProvider.ANTHROPIC.value) == "https://api.anthropic.com/v1/messages"
    assert _get_endpoint(LLMProvider.GOOGLE.value) == "https://generativelanguage.googleapis.com/v1beta/models"
    assert _get_endpoint(LLMProvider.OPENROUTER.value) == "https://openrouter.ai/api/v1/chat/completions"
    assert _get_endpoint(LLMProvider.OLLAMA.value) == "http://localhost:11434/api/chat"


def test_chat_completion_alias_calls_chat(monkeypatch):
    called = {}

    def fake_chat(**kwargs):
        called.update(kwargs)
        return {"text": "ok"}

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    out = llm_client.chat_completion(system_prompt="SYS", user_prompt="USER", max_tokens=12)

    assert out == {"text": "ok"}
    assert called["system_prompt"] == "SYS"
    assert called["user_prompt"] == "USER"
    assert called["max_tokens"] == 12


# ------------------------------------------------------------
# _format_request のテスト
# ------------------------------------------------------------

def test_format_request_openai_with_extra_messages():
    extra = [
        {"role": "assistant", "content": "prev answer"},
        {"content": "implicit user"},  # role 無し → user 扱い
    ]

    payload = _format_request(
        provider=LLMProvider.OPENAI,
        system_prompt="SYS",
        user_prompt="USER",
        model="gpt-4.1-mini",
        temperature=0.1,
        max_tokens=100,
        extra_messages=extra,
    )

    assert payload["model"] == "gpt-4.1-mini"
    assert payload["temperature"] == 0.1
    assert payload["max_tokens"] == 100

    msgs = payload["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "USER"}
    assert msgs[2] == {"role": "assistant", "content": "prev answer"}
    assert msgs[3] == {"role": "user", "content": "implicit user"}


def test_format_request_anthropic_with_extra_messages():
    extra = [
        {"role": "assistant", "content": "A1"},
        {"content": "no role"},  # role 省略 → user 扱い
    ]

    payload = _format_request(
        provider=LLMProvider.ANTHROPIC,
        system_prompt="SYS",
        user_prompt="USER",
        model="claude-3",
        temperature=0.2,
        max_tokens=256,
        extra_messages=extra,
    )

    assert payload["model"] == "claude-3"
    assert payload["max_tokens"] == 256
    assert payload["temperature"] == 0.2
    assert payload["system"] == "SYS"

    msgs = payload["messages"]
    assert msgs[0] == {"role": "user", "content": "USER"}
    assert msgs[1] == {"role": "assistant", "content": "A1"}
    assert msgs[2] == {"role": "user", "content": "no role"}


def test_format_request_gemini_combines_text():
    extra = [
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]

    payload = _format_request(
        provider=LLMProvider.GOOGLE,
        system_prompt="SYS",
        user_prompt="USER",
        model="gemini-pro",
        temperature=0.5,
        max_tokens=256,
        extra_messages=extra,
    )

    assert payload["generationConfig"]["temperature"] == 0.5
    assert payload["generationConfig"]["maxOutputTokens"] == 256

    contents = payload["contents"]
    assert len(contents) == 1
    text = contents[0]["parts"][0]["text"]

    assert "SYS" in text
    assert "USER" in text
    assert "[assistant]" in text
    assert "A1" in text
    assert "[user]" in text
    assert "Q2" in text


def test_format_request_ollama_with_extra_messages():
    extra = [
        {"role": "assistant", "content": "A1"},
        {"content": "implicit"},
    ]

    payload = _format_request(
        provider=LLMProvider.OLLAMA,
        system_prompt="SYS",
        user_prompt="USER",
        model="llama3",
        temperature=0.7,
        max_tokens=128,
        extra_messages=extra,
    )

    assert payload["model"] == "llama3"
    assert "options" in payload
    assert payload["options"]["temperature"] == 0.7

    msgs = payload["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "USER"}
    assert msgs[2] == {"role": "assistant", "content": "A1"}
    assert msgs[3] == {"role": "user", "content": "implicit"}


# ------------------------------------------------------------
# _parse_response のテスト
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "provider,data,expected",
    [
        (
            LLMProvider.OPENAI,
            {"choices": [{"message": {"content": "hello from openai"}}]},
            "hello from openai",
        ),
        (
            LLMProvider.OPENROUTER,
            {"choices": [{"message": {"content": "hello from openrouter"}}]},
            "hello from openrouter",
        ),
        (
            LLMProvider.OLLAMA,
            {"message": {"role": "assistant", "content": "hello from ollama"}},
            "hello from ollama",
        ),
        (
            LLMProvider.ANTHROPIC,
            {"content": [{"type": "text", "text": "hello from claude"}]},
            "hello from claude",
        ),
        (
            LLMProvider.GOOGLE,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "hello from gemini"}]}}
                ]
            },
            "hello from gemini",
        ),
    ],
)
def test_parse_response_various_providers(provider, data, expected):
    text = _parse_response(provider, data)
    assert text == expected


def test_parse_response_anthropic_invalid_raises():
    with pytest.raises(LLMError):
        _parse_response(LLMProvider.ANTHROPIC, {"content": []})


def test_parse_response_gemini_invalid_raises():
    with pytest.raises(LLMError):
        _parse_response(LLMProvider.GOOGLE, {"candidates": []})


def test_parse_response_ollama_invalid_raises():
    with pytest.raises(LLMError):
        _parse_response(LLMProvider.OLLAMA, {})


# ------------------------------------------------------------
# _get_headers のテスト
# ------------------------------------------------------------

def test_get_headers_openai_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-123")
    h = _get_headers(LLMProvider.OPENAI.value)
    assert h["Authorization"] == "Bearer sk-123"
    assert h["Content-Type"] == "application/json"


def test_get_headers_openai_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_API_KEY", raising=False)
    with pytest.raises(LLMError):
        _get_headers(LLMProvider.OPENAI.value)


def test_get_headers_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-123")
    h = _get_headers(LLMProvider.ANTHROPIC.value)
    assert h["x-api-key"] == "ak-123"
    assert h["anthropic-version"] == "2023-06-01"


def test_get_headers_anthropic_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError):
        _get_headers(LLMProvider.ANTHROPIC.value)


def test_get_headers_google(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "gk-123")
    h = _get_headers(LLMProvider.GOOGLE.value)
    assert h["Content-Type"] == "application/json"


def test_get_headers_google_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError):
        _get_headers(LLMProvider.GOOGLE.value)


def test_get_headers_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "ork-123")
    h = _get_headers(LLMProvider.OPENROUTER.value)
    assert h["Authorization"] == "Bearer ork-123"


def test_get_headers_openrouter_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError):
        _get_headers(LLMProvider.OPENROUTER.value)


def test_get_headers_ollama():
    h = _get_headers(LLMProvider.OLLAMA.value)
    assert h["Content-Type"] == "application/json"


# ------------------------------------------------------------
# chat() の成功パス（各プロバイダー）
# ------------------------------------------------------------

def test_chat_openai_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_post(url, headers, json, timeout):
        assert url == "https://api.openai.com/v1/chat/completions"
        assert "Authorization" in headers
        data = {
            "choices": [
                {
                    "message": {"content": "OK from OpenAI"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    res = llm_client.chat(
        system_prompt="SYS",
        user_prompt="USER",
        provider=LLMProvider.OPENAI.value,
        model="gpt-4.1-mini",
    )

    assert res["text"] == "OK from OpenAI"
    assert res["provider"] == LLMProvider.OPENAI.value
    assert res["model"] == "gpt-4.1-mini"
    assert res["finish_reason"] == "stop"
    assert res["usage"]["prompt_tokens"] == 10
    assert res["usage"]["completion_tokens"] == 5


def test_chat_anthropic_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")

    def fake_post(url, headers, json, timeout):
        assert url == "https://api.anthropic.com/v1/messages"
        assert headers["x-api-key"] == "ak-test"
        data = {
            "content": [{"type": "text", "text": "hi from claude"}],
            "stop_reason": "end",
            "usage": {"input_tokens": 1},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    res = llm_client.chat(
        system_prompt="SYS",
        user_prompt="USER",
        provider=LLMProvider.ANTHROPIC.value,
        model="claude-3-sonnet",
    )

    assert res["text"] == "hi from claude"
    assert res["provider"] == LLMProvider.ANTHROPIC.value
    assert res["finish_reason"] == "end"
    assert res["usage"]["input_tokens"] == 1


def test_chat_gemini_success(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "gk-test")
    seen = {}

    def fake_post(url, headers, json, timeout):
        # model が URL に埋め込まれ、API keyはヘッダー経由
        seen["url"] = url
        seen["headers"] = headers
        assert "gemini-pro" in url
        assert "key=" not in url  # URLにキーは含まれない
        assert headers.get("x-goog-api-key") == "gk-test"  # ヘッダーで認証
        data = {
            "candidates": [
                {"content": {"parts": [{"text": "hi from gemini"}]}}
            ],
            "usageMetadata": {"input": 123},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    res = llm_client.chat(
        system_prompt="SYS",
        user_prompt="USER",
        provider=LLMProvider.GOOGLE.value,
        model="gemini-pro",
    )

    assert "generateContent" in seen["url"]
    assert res["text"] == "hi from gemini"
    assert res["provider"] == LLMProvider.GOOGLE.value
    assert res["usage"]["input"] == 123


def test_chat_ollama_success(monkeypatch):
    def fake_post(url, headers, json, timeout):
        assert url == "http://localhost:11434/api/chat"
        data = {
            "message": {"role": "assistant", "content": "hi local"},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    res = llm_client.chat(
        system_prompt="SYS",
        user_prompt="USER",
        provider=LLMProvider.OLLAMA.value,
        model="llama3",
    )

    assert res["text"] == "hi local"
    assert res["provider"] == LLMProvider.OLLAMA.value
    # usage / finish_reason は None のはず
    assert res["usage"] is None
    assert res["finish_reason"] is None


def test_chat_openrouter_success(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "ork-test")

    def fake_post(url, headers, json, timeout):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert headers["Authorization"] == "Bearer ork-test"
        data = {
            "choices": [
                {
                    "message": {"content": "hi from openrouter"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"tokens": 42},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    res = llm_client.chat(
        system_prompt="SYS",
        user_prompt="USER",
        provider=LLMProvider.OPENROUTER.value,
        model="some-model",
    )

    assert res["text"] == "hi from openrouter"
    assert res["finish_reason"] == "stop"
    assert res["usage"]["tokens"] == 42


def test_chat_uses_default_provider_and_model(monkeypatch):
    # デフォルトは LLM_PROVIDER / LLM_MODEL を使う
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", LLMProvider.OPENAI.value)
    monkeypatch.setattr(llm_client, "LLM_MODEL", "gpt-4.1-mini")

    def fake_post(url, headers, json, timeout):
        assert json["model"] == "gpt-4.1-mini"
        data = {
            "choices": [
                {"message": {"content": "default path"}, "finish_reason": "stop"}
            ],
            "usage": {},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    res = llm_client.chat(system_prompt="SYS", user_prompt="USER")
    assert res["text"] == "default path"
    assert res["model"] == "gpt-4.1-mini"


# ------------------------------------------------------------
# chat() のリトライ・エラーパス
# ------------------------------------------------------------

def test_chat_openai_rate_limit_then_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return _DummyResponse(
                status_code=429,
                data={},
                text="rate limited",
            )
        data = {
            "choices": [
                {
                    "message": {"content": "after retry"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }
        return _DummyResponse(status_code=200, data=data, text="ok")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_args, **_kwargs: None)

    res = llm_client.chat("SYS", "USER", provider=LLMProvider.OPENAI.value)
    assert res["text"] == "after retry"
    assert calls["n"] == 2


def test_chat_http_error_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_post(url, headers, json, timeout):
        return _DummyResponse(
            status_code=500,
            data={"error": "server error"},
            text="server error",
        )

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    with pytest.raises(LLMError) as exc:
        llm_client.chat("SYS", "USER", provider=LLMProvider.OPENAI.value)

    assert "API error" in str(exc.value) and "500" in str(exc.value)


def test_chat_request_exception_retries_and_fails(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_post(url, headers, json, timeout):
        raise requests.exceptions.Timeout("boom timeout")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(llm_client, "LLM_MAX_RETRIES", 2)

    with pytest.raises(LLMError) as exc:
        llm_client.chat("SYS", "USER", provider=LLMProvider.OPENAI.value)

    msg = str(exc.value)
    assert "failed after" in msg
    assert "Timeout" in msg


def test_chat_unexpected_error_wraps(monkeypatch):
    """_parse_response などで例外 → LLMError で wrap されるか"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class BadResponse(_DummyResponse):
        def json(self):
            # json() 自体が壊れているケース
            raise ValueError("bad json")

    def fake_post(url, headers, json, timeout):
        return BadResponse(status_code=200, data={})

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    with pytest.raises(LLMError) as exc:
        llm_client.chat("SYS", "USER", provider=LLMProvider.OPENAI.value)

    assert "Failed to parse LLM response as JSON" in str(exc.value)


# ------------------------------------------------------------
# ショートカット関数のテスト
# ------------------------------------------------------------

def test_chat_openai_shortcut(monkeypatch):
    called = {}

    def fake_chat(system_prompt, user_prompt, provider, **kwargs):
        called["provider"] = provider
        called["system"] = system_prompt
        called["user"] = user_prompt
        return {"text": "ok", "provider": provider, "model": kwargs.get("model")}

    monkeypatch.setattr(llm_client, "chat", fake_chat)

    res = llm_client.chat_openai("SYS", "USER")
    assert called["provider"] == LLMProvider.OPENAI.value
    assert called["system"] == "SYS"
    assert called["user"] == "USER"
    assert res["provider"] == LLMProvider.OPENAI.value


def test_chat_gpt4_mini_shortcut(monkeypatch):
    called = {}

    def fake_chat_openai(system_prompt, user_prompt, **kwargs):
        called["system"] = system_prompt
        called["user"] = user_prompt
        called["model"] = kwargs.get("model")
        return {"text": "ok", "provider": "openai", "model": kwargs.get("model")}

    monkeypatch.setattr(llm_client, "chat_openai", fake_chat_openai)

    res = llm_client.chat_gpt4_mini("SYS", "USER")
    assert called["model"] == "gpt-4.1-mini"
    assert res["model"] == "gpt-4.1-mini"


def test_chat_claude_shortcut(monkeypatch):
    called = {}

    def fake_chat(system_prompt, user_prompt, provider, **kwargs):
        called["provider"] = provider
        called["model"] = kwargs.get("model")
        return {"text": "ok", "provider": provider, "model": kwargs.get("model")}

    monkeypatch.setattr(llm_client, "chat", fake_chat)

    res = llm_client.chat_claude("SYS", "USER")
    assert called["provider"] == LLMProvider.ANTHROPIC.value
    assert called["model"] == "claude-3-sonnet-20240229"
    assert res["model"] == "claude-3-sonnet-20240229"


def test_chat_gemini_shortcut(monkeypatch):
    called = {}

    def fake_chat(system_prompt, user_prompt, provider, **kwargs):
        called["provider"] = provider
        called["model"] = kwargs.get("model")
        return {"text": "ok", "provider": provider, "model": kwargs.get("model")}

    monkeypatch.setattr(llm_client, "chat", fake_chat)

    res = llm_client.chat_gemini("SYS", "USER")
    assert called["provider"] == LLMProvider.GOOGLE.value
    assert called["model"] == "gemini-pro"
    assert res["model"] == "gemini-pro"


def test_chat_local_shortcut(monkeypatch):
    called = {}

    def fake_chat(system_prompt, user_prompt, provider, **kwargs):
        called["provider"] = provider
        called["model"] = kwargs.get("model")
        return {"text": "ok", "provider": provider, "model": kwargs.get("model")}

    monkeypatch.setattr(llm_client, "chat", fake_chat)

    res = llm_client.chat_local("SYS", "USER")
    assert called["provider"] == LLMProvider.OLLAMA.value
    assert called["model"] == "llama3"
    assert res["model"] == "llama3"



def test_env_parsing_safe_helpers_return_default_for_invalid_values(monkeypatch):
    monkeypatch.setenv("VERITAS_TEST_SAFE_INT", "invalid-int")
    monkeypatch.setenv("VERITAS_TEST_SAFE_FLOAT", "invalid-float")

    assert llm_client._safe_int("VERITAS_TEST_SAFE_INT", 7) == 7
    assert llm_client._safe_float("VERITAS_TEST_SAFE_FLOAT", 1.5) == 1.5


def test_env_parsing_failsafe_on_module_reload(monkeypatch):
    original_timeout = llm_client.LLM_TIMEOUT
    original_connect_timeout = llm_client.LLM_CONNECT_TIMEOUT
    original_retries = llm_client.LLM_MAX_RETRIES
    original_retry_delay = llm_client.LLM_RETRY_DELAY
    original_max_response_bytes = llm_client.LLM_MAX_RESPONSE_BYTES

    monkeypatch.setenv("LLM_TIMEOUT", "not-a-number")
    monkeypatch.setenv("LLM_CONNECT_TIMEOUT", "bad")
    monkeypatch.setenv("LLM_MAX_RETRIES", "oops")
    monkeypatch.setenv("LLM_RETRY_DELAY", "bad-float")
    monkeypatch.setenv("LLM_MAX_RESPONSE_BYTES", "nope")

    reloaded = importlib.reload(llm_client)
    try:
        assert reloaded.LLM_TIMEOUT == 60.0
        assert reloaded.LLM_CONNECT_TIMEOUT == 10.0
        assert reloaded.LLM_MAX_RETRIES == 3
        assert reloaded.LLM_RETRY_DELAY == 2.0
        assert reloaded.LLM_MAX_RESPONSE_BYTES == 16 * 1024 * 1024
    finally:
        monkeypatch.setenv("LLM_TIMEOUT", str(original_timeout))
        monkeypatch.setenv("LLM_CONNECT_TIMEOUT", str(original_connect_timeout))
        monkeypatch.setenv("LLM_MAX_RETRIES", str(original_retries))
        monkeypatch.setenv("LLM_RETRY_DELAY", str(original_retry_delay))
        monkeypatch.setenv("LLM_MAX_RESPONSE_BYTES", str(original_max_response_bytes))
        importlib.reload(llm_client)
