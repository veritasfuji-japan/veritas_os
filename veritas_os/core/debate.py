# veritas/core/debate.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json, textwrap

from . import llm_client
from . import world as world_model
from . import memory as mem


def _build_system_prompt() -> str:
    """
    DebateOS 用 system プロンプト。
    内部では「楽観」「悲観」「安全チェック」の3視点で考えてよいが、
    最終的な出力はシンプルな JSON 1個にまとめる。
    """
    return textwrap.dedent("""
    あなたは「VERITAS OS」の Debate モジュールです。
    役割は、すでに選択されたアクション候補 (chosen) と、
    他の候補 (alternatives) を比較し、

    - chosen が妥当かどうか
    - どんなリスクや懸念があるか
    - 他の候補を採用すべきか

    を、冷静かつ安全第一で評価することです。

    内部では「楽観的な視点」「懐疑的な視点」「安全・倫理の視点」の
    3つの立場から検討しても構いませんが、
    最終的な出力は必ず次の JSON 形式「だけ」にまとめてください：

    {
      "summary": "なぜこの判断をしたかの日本語要約（3〜6文）",
      "risk_delta": 0.0,
      "suggested_choice_id": null,
      "notes": [
        "気をつけるべき点の bullet を1〜5個",
        "..."
      ]
    }

    - risk_delta は -0.5〜+0.5 の範囲で、基準リスクに対する補正値です。
      例: もっと危なそうなら +0.1、安全寄りなら -0.05 など。
    - suggested_choice_id には、もし別の選択肢を推したい場合に、
      その候補の id を入れてください。なければ null のままにします。
    - notes には、実行時に注意すべきポイントを書いてください。
    - それ以外のフィールドは追加しないでください。
    """)


def _build_user_prompt(
    query: str,
    context: Dict[str, Any],
    chosen: Dict[str, Any],
    alts: List[Dict[str, Any]],
    world: Dict[str, Any] | None,
    mem_text: Optional[str],
) -> str:
    q = (query or "").strip()

    ctx_snip = json.dumps(
        {
            "stakes": context.get("stakes"),
            "telos_weights": context.get("telos_weights"),
            "user_id": context.get("user_id") or "anon",
        },
        ensure_ascii=False,
        indent=2,
    )

    chosen_snip = json.dumps(chosen or {}, ensure_ascii=False, indent=2)
    alts_snip = json.dumps(alts or [], ensure_ascii=False, indent=2)
    world_snip = json.dumps(world or {}, ensure_ascii=False, indent=2)
    mem_snip = mem_text or "(重要メモなし)"

    return textwrap.dedent(f"""
    # ユーザーからの問い / 状況

    {q}

    ---

    # VERITAS の文脈（抜粋）

    {ctx_snip}

    ---

    # WorldModel スナップショット

    {world_snip}

    ---

    # MemoryOS からの重要メモ（要約）

    {mem_snip}

    ---

    # kernel が選んだ chosen

    {chosen_snip}

    ---

    # 他の alternatives

    {alts_snip}

    ---

    上記を踏まえて、chosen が妥当かどうかを評価してください。
    安全性・現実性・ユーザーの長期的利益の観点から、
    指示された JSON 形式で結果だけを返してください。
    """)


def _safe_json_extract(raw: str) -> Dict[str, Any]:
    """LLM出力から安全にJSONだけ抜き出すユーティリティ。"""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        s = raw.index("{")
        e = raw.rindex("}") + 1
        return json.loads(raw[s:e])
    except Exception:
        return {}


def run_debate(
    context: Dict[str, Any],
    query: str,
    chosen: Dict[str, Any],
    alts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    server.py から呼び出すメイン関数。

    戻り値:
    {
      "summary": str,
      "risk_delta": float,
      "suggested_choice_id": str | null,
      "notes": List[str],
      "raw": str,            # LLM 生出力
      "source": "openai_llm" | "fallback"
    }
    """
    ctx = dict(context or {})

    # ---- WorldModel / MemoryOS 補助情報 ----
    try:
        world_snap = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = {}

    mem_text: Optional[str] = None
    try:
        uid = ctx.get("user_id") or "anon"
        if hasattr(mem, "export_recent_for_prompt"):
            mem_text = mem.export_recent_for_prompt(uid, limit=5)
    except Exception:
        mem_text = None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, ctx, chosen, alts, world_snap, mem_text)

    raw_text = ""
    try:
        res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_messages=None,
            temperature=0.3,
            max_tokens=600,
        )
        raw_text = res.get("text", "") if isinstance(res, dict) else str(res)
        parsed = _safe_json_extract(raw_text) or {}

        summary = parsed.get("summary") or ""
        risk_delta = float(parsed.get("risk_delta", 0.0) or 0.0)
        suggested_choice_id = parsed.get("suggested_choice_id")
        notes = parsed.get("notes") or []

        if not isinstance(notes, list):
            notes = [str(notes)]

        return {
            "summary": str(summary),
            "risk_delta": float(risk_delta),
            "suggested_choice_id": suggested_choice_id,
            "notes": [str(n) for n in notes],
            "raw": raw_text,
            "source": "openai_llm",
        }

    except Exception:
        fb = _fallback_debate()
        fb["raw"] = raw_text
        return fb
