# veritas_os/core/llm_client.py
# -*- coding: utf-8 -*-
"""
LLM クライアント（マルチプロバイダー対応版 / 実運用は gpt-4.1-mini 前提）

現状:
    - 実際に使うのは OpenAI + gpt-4.1-mini（または env で指定した OpenAI モデル）
    - Anthropic / Google / Ollama / OpenRouter は「将来用」のサポートを残す

環境変数:
    LLM_PROVIDER : openai | anthropic | google | ollama | openrouter  (デフォルト: openai)
    LLM_MODEL    : モデル名 (デフォルト: gpt-4.1-mini)
    LLM_TIMEOUT  : API タイムアウト秒 (デフォルト: 60)
    LLM_MAX_RETRIES : 最大リトライ回数 (デフォルト: 3)
    LLM_RETRY_DELAY : リトライ間隔秒 (デフォルト: 2)

    OPENAI_API_KEY     : OpenAI 用 API キー（必須）
    ANTHROPIC_API_KEY  : Claude 用 API キー（将来用）
    GOOGLE_API_KEY     : Gemini 用 API キー（将来用）
    OPENROUTER_API_KEY : OpenRouter 用 API キー（将来用）
"""

from __future__ import annotations

import logging
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional

import requests

from veritas_os.core import affect as affect_core

log = logging.getLogger(__name__)


# =========================
# Enum / 例外
# =========================

class LLMProvider(str, Enum):
    """LLMプロバイダー種類"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


class LLMError(Exception):
    """LLM 呼び出しに関するエラー"""


# =========================
# 設定値（環境変数）
# =========================

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", LLMProvider.OPENAI.value)
# ★ 現在のデフォルトは gpt-4.1-mini を想定（env で上書き可）
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4.1-mini")

LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))
LLM_RETRY_DELAY = float(os.environ.get("LLM_RETRY_DELAY", "2"))


# =========================
# Affect 注入
# =========================

def _inject_affect_into_system_prompt(
    system_prompt: str,
    affect_hint: Optional[str] = None,
    affect_style: Optional[str] = None,
) -> str:
    """
    Affectのスタイル規範を system_prompt 先頭に注入する。

    - affect_style が指定されていれば優先（"legal" など）
    - それ以外は affect_hint から choose_style で推定
    """
    # normalize_style / style_instructions は affect.py の完全版で提供される想定
    if affect_style:
        style_key = affect_core.normalize_style(affect_style)
    else:
        style_key = affect_core.normalize_style(affect_core.choose_style(affect_hint))

    instr = (affect_core.style_instructions(style_key) or "").strip()
    if not instr:
        return system_prompt or ""

    if not system_prompt:
        return instr

    return f"{instr}\n\n{system_prompt}"


# =========================
# 内部ユーティリティ
# =========================

def _get_api_key(provider: str) -> Optional[str]:
    """プロバイダー別の API キー取得"""
    if provider == LLMProvider.OPENAI.value:
        # 互換のため OPEN_API_KEY も fallback
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_API_KEY")
    if provider == LLMProvider.ANTHROPIC.value:
        return os.environ.get("ANTHROPIC_API_KEY")
    if provider == LLMProvider.GOOGLE.value:
        return os.environ.get("GOOGLE_API_KEY")
    if provider == LLMProvider.OPENROUTER.value:
        return os.environ.get("OPENROUTER_API_KEY")
    # Ollama はローカルなので API キー不要
    return None


def _get_endpoint(provider: str) -> str:
    """プロバイダー別のエンドポイント URL"""
    if provider == LLMProvider.OPENAI.value:
        # Chat Completions
        return "https://api.openai.com/v1/chat/completions"
    if provider == LLMProvider.ANTHROPIC.value:
        return "https://api.anthropic.com/v1/messages"
    if provider == LLMProvider.GOOGLE.value:
        # generateContent のベース URL（model 名は後で付与）
        return "https://generativelanguage.googleapis.com/v1beta/models"
    if provider == LLMProvider.OPENROUTER.value:
        return "https://openrouter.ai/api/v1/chat/completions"
    if provider == LLMProvider.OLLAMA.value:
        return "http://localhost:11434/api/chat"
    # デフォルトは OpenAI 相当
    return "https://api.openai.com/v1/chat/completions"


def _format_request(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    extra_messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    プロバイダー別のリクエスト形式に整形

    extra_messages:
        OpenAI系:
            そのまま messages に extend
        Anthropic:
            messages に extend（role/content 付き想定）
        Gemini:
            単純に user_prompt の末尾にテキスト結合（ラフ運用）
        Ollama:
            OpenAI 互換の messages に extend
    """
    extra_messages = extra_messages or []

    if provider == LLMProvider.ANTHROPIC.value:
        msgs: List[Dict[str, str]] = [{"role": "user", "content": user_prompt}]
        for m in extra_messages:
            role = m.get("role") or "user"
            content = m.get("content") or ""
            msgs.append({"role": role, "content": content})

        return {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": msgs,
        }

    if provider == LLMProvider.GOOGLE.value:
        # Gemini generateContent:
        # system + user + extra を 1 テキストにまとめる簡易実装
        extra_text = ""
        for m in extra_messages:
            role = m.get("role") or "user"
            content = m.get("content") or ""
            extra_text += f"\n\n[{role}]\n{content}"

        full_text = f"{system_prompt}\n\n{user_prompt}{extra_text}"

        return {
            "contents": [
                {"parts": [{"text": full_text}]}
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

    if provider == LLMProvider.OLLAMA.value:
        msgs: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        for m in extra_messages:
            role = m.get("role") or "user"
            content = m.get("content") or ""
            msgs.append({"role": role, "content": content})

        return {
            "model": model,
            "messages": msgs,
            "options": {"temperature": temperature},
        }

    # OpenAI / OpenRouter（ほぼ互換）
    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    for m in extra_messages:
        role = m.get("role") or "user"
        content = m.get("content") or ""
        msgs.append({"role": role, "content": content})

    return {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _parse_response(provider: str, data: Dict[str, Any]) -> str:
    """プロバイダー別レスポンスからテキストだけ抽出"""
    if provider == LLMProvider.ANTHROPIC.value:
        # Claude Messages: {"content": [{"type": "text", "text": "..."}], ...}
        try:
            return data["content"][0]["text"]
        except Exception as e:
            raise LLMError(f"Anthropic response parse error: {repr(e)}") from e

    if provider == LLMProvider.GOOGLE.value:
        # Gemini: {"candidates":[{"content":{"parts":[{"text":"..."}]}}]}
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            raise LLMError(f"Gemini response parse error: {repr(e)}") from e

    if provider == LLMProvider.OLLAMA.value:
        # Ollama chat: {"message":{"role":"assistant","content":"..."}}
        # or OpenAI 互換 choices
        if "message" in data:
            return data["message"].get("content", "")
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"]
        raise LLMError("Ollama response format not recognized")

    # OpenAI / OpenRouter 互換
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise LLMError(f"OpenAI-like response parse error: {repr(e)}") from e


def _get_headers(provider: str) -> Dict[str, str]:
    """プロバイダー別ヘッダー生成"""
    api_key = _get_api_key(provider)

    if provider == LLMProvider.ANTHROPIC.value:
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY not set")
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    if provider == LLMProvider.GOOGLE.value:
        if not api_key:
            raise LLMError("GOOGLE_API_KEY not set")
        # Gemini は x-goog-api-key ヘッダーで認証（URLパラメータより安全）
        return {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }

    if provider == LLMProvider.OLLAMA.value:
        return {"Content-Type": "application/json"}

    if provider == LLMProvider.OPENROUTER.value:
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY not set")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    # OpenAI（デフォルト）
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# =========================
# メイン API
# =========================

def chat(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    extra_messages: Optional[List[Dict[str, str]]] = None,
    affect_hint: Optional[str] = None,
    affect_style: Optional[str] = None,
) -> Dict[str, Any]:
    """
    マルチプロバイダー対応 chat コール（実運用は OpenAI + gpt-4.1-mini 前提）

    Args:
        system_prompt: システムメッセージ
        user_prompt  : ユーザーメッセージ
        temperature  : サンプリング温度
        max_tokens   : 最大生成トークン数
        model        : モデル名（省略時は LLM_MODEL）
        provider     : プロバイダー名（省略時は LLM_PROVIDER）
        extra_messages:
            追加のメッセージ履歴（list[{"role": "...", "content": "..."}]）
        affect_hint:
            "弁護士向けに" などの日本語ヒント（choose_style に渡す）
        affect_style:
            "legal" / "warm" / "coach" などを直指定（hintより優先）

    Returns:
        dict:
            {
              "text": "...",
              "provider": "openai",
              "model": "gpt-4.1-mini",
              "finish_reason": "...",
              "usage": {...} | None,
              "raw": {...}
            }
    """
    provider = provider or LLM_PROVIDER
    model = model or LLM_MODEL

    # ★ Affect 注入（必要な時だけ効く）
    system_prompt = _inject_affect_into_system_prompt(
        system_prompt=system_prompt,
        affect_hint=affect_hint,
        affect_style=affect_style,
    )

    endpoint = _get_endpoint(provider)
    headers = _get_headers(provider)
    payload = _format_request(
        provider=provider,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_messages=extra_messages,
    )

    # Gemini は endpoint + model + :generateContent の形式（認証はヘッダー経由）
    if provider == LLMProvider.GOOGLE.value:
        endpoint = f"{endpoint}/{model}:generateContent"

    last_error: Optional[Exception] = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT,
            )

            # レート制限
            if resp.status_code == 429:
                if attempt < LLM_MAX_RETRIES:
                    wait_time = LLM_RETRY_DELAY * (2 ** (attempt - 1))
                    log.warning(
                        "LLM rate limited (provider=%s, attempt=%s), retry in %.1fs",
                        provider,
                        attempt,
                        wait_time,
                    )
                    time.sleep(wait_time)
                    continue
                raise LLMError(f"Rate limited after {LLM_MAX_RETRIES} retries (status=429)")

            # その他エラー
            if resp.status_code >= 400:
                raise LLMError(f"API error (status={resp.status_code})")

            data = resp.json()
            text = _parse_response(provider, data)

            # finish_reason / usage はプロバイダごとに少し違うのでゆるめに取る
            finish_reason = None
            usage = None

            if provider in (LLMProvider.OPENAI.value, LLMProvider.OPENROUTER.value, LLMProvider.OLLAMA.value):
                if "choices" in data and data["choices"]:
                    finish_reason = data["choices"][0].get("finish_reason")
                usage = data.get("usage")
            elif provider == LLMProvider.ANTHROPIC.value:
                finish_reason = data.get("stop_reason")
                usage = data.get("usage")
            elif provider == LLMProvider.GOOGLE.value:
                usage = data.get("usageMetadata")

            return {
                "text": text,
                "provider": provider,
                "model": model,
                "finish_reason": finish_reason,
                "usage": usage,
                "raw": data,
            }

        except requests.exceptions.RequestException as e:
            last_error = e
            wait_time = LLM_RETRY_DELAY * (2 ** (attempt - 1))
            log.warning(
                "LLM request error (provider=%s, attempt=%s), retry in %.1fs: %r",
                provider,
                attempt,
                wait_time,
                e,
            )
            if attempt < LLM_MAX_RETRIES:
                time.sleep(wait_time)
                continue
        except Exception as e:
            # 予期せぬエラーは即終了
            raise LLMError(f"Unexpected error: {repr(e)}") from e

    # 全リトライ失敗
    raise LLMError(
        f"LLM request failed after {LLM_MAX_RETRIES} retries: {repr(last_error)}"
    )


# =========================
# ショートカット関数
# =========================

def chat_openai(system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
    """OpenAI 専用ショートカット（実質これが今の VERITAS のメイン入口）"""
    return chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider=LLMProvider.OPENAI.value,
        **kwargs,
    )


def chat_gpt4_mini(system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
    """
    gpt-4.1-mini 専用ショートカット
    環境変数に関係なく gpt-4.1-mini を強制したい場面用。
    """
    kwargs.setdefault("model", "gpt-4.1-mini")
    return chat_openai(system_prompt, user_prompt, **kwargs)


def chat_claude(system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
    """Claude 用ショートカット（将来用）"""
    kwargs.setdefault("model", "claude-3-sonnet-20240229")
    return chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider=LLMProvider.ANTHROPIC.value,
        **kwargs,
    )


def chat_gemini(system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
    """Gemini 用ショートカット（将来用）"""
    kwargs.setdefault("model", "gemini-pro")
    return chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider=LLMProvider.GOOGLE.value,
        **kwargs,
    )


def chat_local(system_prompt: str, user_prompt: str, **kwargs) -> Dict[str, Any]:
    """Ollama / ローカルモデル用ショートカット（将来用）"""
    kwargs.setdefault("model", "llama3")
    return chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        provider=LLMProvider.OLLAMA.value,
        **kwargs,
    )


__all__ = [
    "LLMProvider",
    "LLMError",
    "chat",
    "chat_openai",
    "chat_gpt4_mini",
    "chat_claude",
    "chat_gemini",
    "chat_local",
]

