# veritas_os/core/llm_client.py
# -*- coding: utf-8 -*-
"""
LLM クライアント（最小 & 安定版）

役割:
- OpenAI 互換の /v1/chat/completions エンドポイントを叩く薄いラッパー
- ベンダーやモデルを変えたいときは、このファイルだけ差し替えればOK

注意:
- VERITAS 専用のプランナー関数 (plan_for_veritas_agi など) は
  planner.py 側に置く。ここは「汎用 LLM 呼び出し」だけに責務を絞る。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

# ===== 設定 (環境変数で上書き可能) =====
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4.1-mini")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))  # 秒


class LLMError(Exception):
    """LLM 呼び出しに関するエラー"""


def _get_api_key() -> str:
    """
    毎回環境変数から API キーを取得する。

    優先順位:
      1. OPEN_API_KEY   (手元でよく使っている名前)
      2. OPENAI_API_KEY (一般的な名前)
    """
    key = (
        os.environ.get("OPEN_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    if not key:
        raise LLMError(
            "OPEN_API_KEY もしくは OPENAI_API_KEY が設定されていません。"
            "例: export OPEN_API_KEY='sk-xxxx'"
        )
    return key


def _headers() -> Dict[str, str]:
    """毎回 API キーを読み直してヘッダを作る"""
    api_key = _get_api_key()
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def chat(
    system_prompt: str,
    user_prompt: str,
    extra_messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.3,
    max_tokens: int = 800,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    汎用 chat 呼び出し。

    Args:
        system_prompt: システムメッセージ
        user_prompt:   ユーザメッセージ
        extra_messages: 追加メッセージ (role/content の dict)
        temperature:   サンプリング温度
        max_tokens:    最大生成トークン数
        model:         個別指定したいモデル名（省略時 LLM_MODEL）
        base_url:      個別指定したいベースURL（省略時 LLM_BASE_URL）

    Returns:
        {
          "text": "...",            # モデルの出力テキスト
          "source": "openai_llm",   # 呼び出し元識別
          "model": "gpt-4.1-mini",  # 実際に使われたモデル
          "finish_reason": "stop",  # API が返した finish_reason (あれば)
          "raw": { ... }            # 生の JSON (必要に応じて利用)
        }

    Raises:
        LLMError: ネットワークエラー、APIエラーなど
    """
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    if extra_messages:
        messages.extend(extra_messages)

    url = f"{(base_url or LLM_BASE_URL).rstrip('/')}/v1/chat/completions"
    model_name = model or LLM_MODEL

    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    try:
        resp = requests.post(
            url,
            headers=_headers(),
            data=json.dumps(payload, ensure_ascii=False),
            timeout=LLM_TIMEOUT,
        )
    except Exception as e:
        # 接続系エラーはここでまとめて LLMError にする
        raise LLMError(f"LLM API request failed: {repr(e)}") from e

    if resp.status_code >= 400:
        # 400系/500系エラー → そのままメッセージを切り詰めて返す
        text_snip = resp.text[:500]
        raise LLMError(
            f"LLM API error {resp.status_code}: {text_snip}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raise LLMError(
            f"LLM API response is not valid JSON: {resp.text[:200]}"
        ) from e

    try:
        choice0 = (data.get("choices") or [])[0]
        msg = choice0.get("message") or {}
        content = msg.get("content") or ""
        finish_reason = choice0.get("finish_reason")
    except Exception as e:
        raise LLMError(
            f"LLM API response format unexpected: {json.dumps(data)[:300]}"
        ) from e

    if not isinstance(content, str) or not content.strip():
        raise LLMError(
            f"LLM returned empty content: {json.dumps(data)[:300]}"
        )

    result: Dict[str, Any] = {
        "text": content,
        "source": "openai_llm",
        "model": data.get("model", model_name),
        "finish_reason": finish_reason,
        "raw": data,
    }

    # デバッグしたいときだけログを有効化
    if os.environ.get("VERITAS_LLM_DEBUG", "0") == "1":
        log.info("[LLM] model=%s finish=%s", result["model"], finish_reason)
        log.debug("[LLM] text=%s", content[:200].replace("\n", "\\n"))

    return result

