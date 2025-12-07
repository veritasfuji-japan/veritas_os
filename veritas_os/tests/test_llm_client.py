# tests/test_llm_client.py
from unittest.mock import patch, MagicMock

from veritas_os.core import llm_client


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

