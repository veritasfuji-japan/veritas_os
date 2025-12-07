# tests/test_llm_client.py
from unittest.mock import patch, MagicMock

from veritas_os.core import llm_client

import os
import pytest
import requests

from veritas_os.core import llm_client
from veritas_os.core.llm_client import (
    LLMProvider,
    LLMError,
    _format_request,
    _parse_response,
)


@patch("veritas_os.core.llm_client.requests.post")
def test_chat_openai_basic(mock_post, monkeypatch):
    # 環境変数セット（APIキーだけあればよい）
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")

    # ダミーレスポンス
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [
            {"message": {"content": "hello from fake model"}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    mock_post.return_value = fake_resp

    res = llm_client.chat_openai("system", "user")

    assert res["text"] == "hello from fake model"
    assert res["provider"] == "openai"
    assert res["model"] == "gpt-4.1-mini"




# =========================
# _format_request のテスト
# =========================

def test_format_request_openai_with_extra_messages():
    extra = [
        {"role": "assistant", "content": "prev answer"},
        {"content": "implicit user"},  # role 無し → user 扱いになるはず
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

    # 基本構造
    assert payload["model"] == "gpt-4.1-mini"
    assert payload["temperature"] == 0.1
    assert payload["max_tokens"] == 100

    msgs = payload["messages"]
    # 先頭2つは system / user
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "USER"}

    # extra_messages が順に追加されているか
    assert msgs[2] == {"role": "assistant", "content": "prev answer"}
    # role 省略時は user 扱い
    assert msgs[3] == {"role": "user", "content": "implicit user"}


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

    # system / user / extra が 1 テキストにまとまっていることだけ確認
    assert "SYS" in text
    assert "USER" in text
    assert "[assistant]" in text
    assert "A1" in text
    assert "[user]" in text
    assert "Q2" in text


# =========================
# _parse_response のテスト
# =========================

@pytest.mark.parametrize(
    "provider,data,expected",
    [
        (
            LLMProvider.OPENAI,
            {"choices": [{"message": {"content": "hello from openai"}}]},
            "hello from openai",
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
    # content 構造が壊れている場合は LLMError になるはず
    with pytest.raises(LLMError):
        _parse_response(
            LLMProvider.ANTHROPIC,
            {"content": []},  # index 0 が無い
        )


# =========================
# chat(OpenAI) のテスト
# =========================

class _DummyResponse:
    def __init__(self, status_code: int, data: dict, text: str = ""):
        self.status_code = status_code
        self._data = data
        self.text = text or ""

    def json(self):
        return self._data


def test_chat_openai_success(monkeypatch):
    # APIキーを強制的にセット
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_post(url, headers, json, timeout):
        # Authorization ヘッダが付いていることだけ軽くチェック
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
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

    res = llm_client.chat_openai("SYS", "USER")

    assert res["text"] == "OK from OpenAI"
    assert res["provider"] == LLMProvider.OPENAI
    assert res["model"] == "gpt-4.1-mini"  # デフォルトモデル
    assert res["finish_reason"] == "stop"
    assert res["usage"]["prompt_tokens"] == 10
    assert res["usage"]["completion_tokens"] == 5


def test_chat_openai_rate_limit_then_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            # 1回目は 429 → リトライさせたい
            return _DummyResponse(
                status_code=429,
                data={},
                text="rate limited",
            )
        # 2回目で成功
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
    # 実際の sleep は飛ばしてテスト高速化
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_args, **_kwargs: None)

    res = llm_client.chat_openai("SYS", "USER")

    assert res["text"] == "after retry"
    # 429 → 200 の 2回呼ばれているはず
    assert calls["n"] == 2


def test_chat_openai_all_retries_fail(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # 常に RequestException（Timeout）を投げる
    def fake_post(url, headers, json, timeout):
        raise requests.exceptions.Timeout("boom timeout")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_args, **_kwargs: None)

    with pytest.raises(LLMError) as exc:
        llm_client.chat_openai("SYS", "USER")

    msg = str(exc.value)
    # リトライ後に LLMError になることだけ確認
    assert "failed after" in msg
    assert "Timeout" in msg
