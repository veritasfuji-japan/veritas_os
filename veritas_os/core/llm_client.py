# veritas/core/llm_client.py
"""
LLM クライアント（最小版）
- OpenAI 互換の /v1/chat/completions エンドポイントを叩く前提
- ベンダーを変えたくなったら、このファイルだけ差し替えればOK
"""

import os
import json
import requests
from typing import Any, Dict, List, Optional
from openai import OpenAI

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com")
LLM_MODEL    = os.environ.get("LLM_MODEL", "gpt-4.1-mini")


class LLMError(Exception):
    pass


def _get_api_key() -> str:
    """
    毎回環境変数から API キーを取得する。
    - OPEN_API_KEY があればそれを優先
    - なければ OPENAI_API_KEY も試す
    """
    key = (
        os.environ.get("OPEN_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    # デバッグ用ログ（1 回だけ見たいならコメントアウトしてもOK）
    # print("[LLM] OPEN_API_KEY from env:", repr(key))

    if not key:
        raise LLMError("OPEN_API_KEY が設定されていません。export してください。")
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
) -> Dict[str, str]:
    """
    汎用 chat 呼び出し
    """
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    if extra_messages:
        messages.extend(extra_messages)

    url = f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    resp = requests.post(url, headers=_headers(), data=json.dumps(payload))
    if resp.status_code >= 400:
        raise LLMError(f"LLM API error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return {
        "text": text,
        "source": "openai_llm",
    }


def plan_for_veritas_agi(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    VERITAS の AGI化プロジェクト専用の「プラン生成」API。
    - /v1/decide から呼ばれる想定。
    - 返り値は {steps: [...], note: "..."} の形にパースして返す。
    """
    system_prompt = """\
あなたは『VERITAS（プロトAGI OS）』専属のテクニカルプランナーです。

【重要なルール】
- 出力は必ず **JSON だけ** を返してください。
- JSON の前後に日本語の説明やコードブロック記法```は絶対に書かないでください。
- 改行やスペースは JSON 内だけにしてください。

JSON スキーマ:
{
  "steps": [
    {
      "id": "step01",
      "title": "ファイルを作成する",
      "detail": "veritas/core/xxx.py を作成し、〜〜の処理を書く",
      "category": "coding"
    }
  ],
  "note": "補足コメント"
}
"""

    # コンテキストの一部もヒントとして渡す
    ctx_summary = {
        "user_id": (context or {}).get("user_id"),
        "world": (context or {}).get("world"),
        "project": "VERITAS_AGI",
    }
    user_prompt = f"現在のクエリ: {query}\n\ncontext概要: {json.dumps(ctx_summary, ensure_ascii=False)}"

    # ---- LLM 呼び出し ----
    raw = chat(system_prompt, user_prompt, temperature=0.25, max_tokens=900)
    # chat() は {"text": "...", "source": "openai_llm"} を返す前提
    raw_text = raw.get("text", "")
    # デバッグログ（邪魔ならコメントアウト）
    print("[PlannerOS] raw_text:", raw_text[:200])

    # ---- JSON パースを強制するユーティリティ ----
    def _safe_parse_json(s: str) -> Dict[str, Any]:
        # まず素直にトライ
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 失敗した場合: 最初の '{' 〜 最後の '}' を抜き出して再トライ
        try:
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                sub = s[start : end + 1]
                obj = json.loads(sub)
                if isinstance(obj, dict):
                    return obj
        except Exception:
            pass

        # それでもダメなら空骨格
        return {
            "steps": [],
            "note": f"LLM 出力を JSON としてパースできませんでした",
        }

    # ---- 実際にパース ----
    obj = _safe_parse_json(raw_text)

    # steps 正規化
    steps = obj.get("steps") or []
    if not isinstance(steps, list):
        steps = []

    norm_steps: List[Dict[str, Any]] = []
    for i, st in enumerate(steps, start=1):
        if not isinstance(st, dict):
            continue
        norm_steps.append(
            {
                "id": st.get("id") or f"step{i:02d}",
                "title": st.get("title") or st.get("name") or f"Step {i}",
                "detail": st.get("detail") or st.get("description") or "",
                "category": st.get("category") or "task",
            }
        )

    return {
        "steps": norm_steps,
        "note": obj.get("note") or "",
        "raw": raw_text,
    }
