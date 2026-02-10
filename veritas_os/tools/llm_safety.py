# veritas_os/tools/llm_safety.py
# -*- coding: utf-8 -*-
"""
llm_safety tool

FUJI Gate から呼ばれる「安全ヘッド」。
- 可能なら OpenAI などの LLM を使って安全判定
- 使えない場合はローカルの簡易ヒューリスティックにフォールバック

戻り値フォーマット（fuji.run_safety_head からの期待値）:

{
  "ok": True,
  "risk_score": 0.23,              # 0〜1
  "categories": ["PII", "illicit"],
  "rationale": "短い理由文",
  "model": "gpt-4.1-mini",
  "raw": {...}                     # モデル生出力 or 追加情報
}
"""

from __future__ import annotations
from typing import Any, Dict, List
import json
import os
import re
import time

try:
    # OpenAI クライアント（インポートできなければ使わない）
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


# -------------------------------
# ヒューリスティック用キーワード
# -------------------------------
_BANNED = {
    "harm",
    "kill",
    "exploit",
    "illegal",
    "weapon",
    "malware",
    "bomb",
    "doxx",
    "毒",
    "殺",
    "爆弾",
    "銃",
    "兵器",
    "ハッキング",
    "違法",
}
_SENSITIVE = {
    "bio", "pathogen", "drug synthesis", "zero-day", "bypass", "unlock jail",
    "生物兵器", "毒物合成", "ゼロデイ", "脱獄", "暗号回避",
}

_RE_PHONE  = re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_RE_ADDRJP = re.compile(r'(東京都|道府県|市|区|町|村).{0,20}\d')
# ★ 修正: 漢字2〜4文字だけでは日本語テキスト全般にマッチして偽陽性が多すぎるため、
# 敬称（さん/様/氏/先生/殿）付きの名前パターンに限定する（sanitize.py と同様のアプローチ）
# 例: "山田太郎さん", "田中 様", "鈴木先生"
_RE_NAMEJP = re.compile(r'[\u4e00-\u9fff]{2,4}\s*(?:さん|様|氏|先生|殿)')


def _norm(s: str) -> str:
    return (s or "").replace("　", " ").strip().lower()


def _heuristic_analyze(text: str) -> Dict[str, Any]:
    """LLM が使えない場合の簡易ヘッド。"""
    t = _norm(text)
    categories: List[str] = []
    risk = 0.05
    reasons: List[str] = []

    hits_b = [w for w in _BANNED if w in t]
    hits_s = [w for w in _SENSITIVE if w in t]
    if hits_b or hits_s:
        categories.append("illicit")
        risk = max(risk, 0.8)
        reasons.append(
            f"危険/違法寄りワード検出: {', '.join(sorted(set(hits_b + hits_s)))}"
        )

    pii_hits: List[str] = []
    if _RE_PHONE.search(text):
        pii_hits.append("phone")
    if _RE_EMAIL.search(text):
        pii_hits.append("email")
    if _RE_ADDRJP.search(text):
        pii_hits.append("address")
    if _RE_NAMEJP.search(text):
        pii_hits.append("name_like")

    if pii_hits:
        categories.append("PII")
        risk = max(risk, 0.35)
        reasons.append(f"PII パターン検出: {', '.join(pii_hits)}")

    if not categories:
        reasons.append("特に危険ワード/PII パターンは検出されませんでした。")

    return {
        "ok": True,
        "risk_score": min(1.0, risk),
        "categories": sorted(set(categories)),
        "rationale": " / ".join(reasons),
        "model": "heuristic_fallback",
        "raw": {
            "fallback": True,
            "banned_hits": hits_b + hits_s,
            "pii_hits": pii_hits,
        },
    }


def _score_risk(
    *,
    llm_risk: float,
    llm_categories: List[str],
    heuristic: Dict[str, Any],
) -> Dict[str, Any]:
    """
    LLM 出力とヒューリスティックを決定論的に合成する。

    - リスクは max(llm_risk, heuristic_risk) をベースに固定ルールで補正
    - カテゴリは LLM を優先しつつ重複しない形で併合
    """
    heuristic_risk = float(heuristic.get("risk_score", 0.0) or 0.0)
    heuristic_categories = [str(c) for c in (heuristic.get("categories") or [])]

    combined_categories = list(llm_categories)
    for cat in heuristic_categories:
        if cat not in combined_categories:
            combined_categories.append(cat)

    notes: List[str] = []
    combined_risk = max(llm_risk, heuristic_risk)

    if heuristic_risk > llm_risk:
        combined_risk = min(1.0, heuristic_risk + 0.05)
        notes.append("heuristic_risk_override")

    if "illicit" in heuristic_categories and "illicit" not in llm_categories:
        combined_risk = min(1.0, max(combined_risk, 0.7))
        notes.append("illicit_floor")

    return {
        "risk_score": combined_risk,
        "categories": combined_categories,
        "heuristic_risk": heuristic_risk,
        "notes": notes,
    }


def _llm_available() -> bool:
    if OpenAI is None:
        return False
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_VERITAS")
    return bool(api_key)


def _analyze_with_llm(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
    max_categories: int = 5,
) -> Dict[str, Any]:
    """
    OpenAI Responses API などを使った「ちゃんとした安全ヘッド」。
    モデル名は VERITAS_SAFETY_MODEL で差し替え可能。
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_VERITAS")
    if not api_key:  # 念のため再チェック
        raise RuntimeError("OPENAI_API_KEY not set for llm_safety")

    model_name = os.getenv("VERITAS_SAFETY_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)

    # context から stakes 等を軽く渡してあげる
    ctx = context or {}
    stakes = float(ctx.get("stakes", 0.5) or 0.5)

    system = (
        "You are a safety classification head for an AI system called VERITAS.\n"
        "Your job is ONLY to classify the RISK of a given text, NOT to answer it.\n"
        "Output a short JSON with: risk_score (0-1), categories, rationale.\n"
        "Think in terms of OpenAI-like safety categories: PII, self_harm, illicit, violence, hate, minors, etc."
    )

    user_payload = {
        "text": text,
        "stakes": stakes,
        "alternatives_preview": [
            a.get("title") or a.get("description") or ""
            for a in (alternatives or [])[:5]
        ],
    }

    t0 = time.time()
    resp = client.responses.create(
        model=model_name,
        reasoning={"effort": "low"},
        temperature=0,
        input=[
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": f"CLASSIFY_THIS_INPUT:\n```json\n{json.dumps(user_payload, ensure_ascii=False)}\n```",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "safety_head_output",
                "schema": {
                    "type": "object",
                    "properties": {
                        "risk_score": {"type": "number"},
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["risk_score", "categories", "rationale"],
                    "additionalProperties": True,
                },
                "strict": False,
            },
        },
    )
    latency_ms = int((time.time() - t0) * 1000)

    # Responses API の JSON 抜き出し
    # ★ H-5 修正: output が空の場合の IndexError を防止
    output = getattr(resp, "output", None)
    if not output or len(output) == 0:
        raise RuntimeError("LLM safety head returned empty output")
    out = output[0].parsed  # type: ignore[attr-defined]
    if out is None:
        raise RuntimeError("LLM safety head returned unparseable output")

    risk = float(out.get("risk_score", 0.05) or 0.05)
    cats = out.get("categories") or []
    rat = out.get("rationale") or ""

    heuristic = _heuristic_analyze(text)
    scoring = _score_risk(
        llm_risk=risk,
        llm_categories=[str(c) for c in cats],
        heuristic=heuristic,
    )
    scored_categories = scoring["categories"][:max_categories]
    scored_risk = float(scoring["risk_score"])
    scoring_notes = scoring.get("notes") or []
    if scoring_notes:
        rat = f"{rat} / scoring={'|'.join(scoring_notes)}"

    return {
        "ok": True,
        "risk_score": max(0.0, min(1.0, scored_risk)),
        "categories": scored_categories,
        "rationale": str(rat),
        "model": model_name,
        "raw": {
            "latency_ms": latency_ms,
            "scoring": {
                "llm_risk": risk,
                "heuristic_risk": scoring.get("heuristic_risk"),
                "notes": scoring_notes,
            },
            "response": resp.model_dump_json(),  # 監査用
        },
    }


def run(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
    max_categories: int = 5,
) -> Dict[str, Any]:
    """
    call_tool("llm_safety", ...) から呼ばれるエントリポイント。
    """
    # 強制ヒューリスティックモード（テスト・オフライン用）
    if os.getenv("VERITAS_SAFETY_MODE", "").lower() in {"heuristic", "local"}:
        return _heuristic_analyze(text)

    if _llm_available():
        try:
            return _analyze_with_llm(
                text=text,
                context=context,
                alternatives=alternatives,
                max_categories=max_categories,
            )
        except Exception as e:
            # LLM 失敗時は fallback
            fb = _heuristic_analyze(text)
            fb["ok"] = True
            fb.setdefault("raw", {})["llm_error"] = f"{type(e).__name__}: {e}"
            return fb

    # API キー不在など → ヒューリスティック
    return _heuristic_analyze(text)
