from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import time
from datetime import datetime

from . import llm_client 

# ============================
# ログパスは「このリポジトリ内」のみを見る
# ============================

# REPO_ROOT = .../veritas_clean_test2/veritas_os
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ここでは VERITAS_LOG_DIR を無視して固定パスにする
LOG_DIR = SCRIPTS_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

META_LOG = LOG_DIR / "meta_log.json"
print("[ReasonOS] META_LOG path:", META_LOG)

def reflect(decision: Dict[str, Any]) -> Dict[str, Any]:
    """
    決定結果を自己評価し、次回に活かす“改善勘所”を返す。
    ルールは軽量：FUJI・Value・実効リスク・採択案の整合を点検。
    """
    q         = (decision.get("query") or "").lower()
    chosen    = decision.get("chosen") or {}
    gate      = decision.get("gate")   or {}
    values    = decision.get("values") or {}
    ema       = float(values.get("ema", values.get("total", 0.5)))
    risk      = float(gate.get("risk", 0.0))
    status    = (gate.get("decision_status") or "allow").lower()

    tips: List[str] = []
    if risk >= 0.6:
        tips.append("高リスク：情報源を1次資料で補強")
    if ema < 0.55:
        tips.append("低価値EMA：ユーザ便益と根拠提示を強化")
    if status == "rejected":
        tips.append("拒否：代替案生成（safe-variant）を次回強制")

    # “次回ブースト”を数値化（-0.1〜+0.1）
    boost = 0.0
    if "情報収集" in (chosen.get("title") or ""):
        boost += 0.05
    if risk >= 0.6: boost -= 0.05
    if ema >= 0.7:  boost += 0.05

    out = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "query": q[:200],
        "chosen_title": chosen.get("title"),
        "status": status,
        "risk": round(risk,3),
        "ema": round(ema,3),
        "improvement_tips": tips,
        "next_value_boost": round(boost,3),
    }
    with open(META_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False)+"\n")
    return out
def generate_reason(*, query, planner=None, values=None, gate=None, context=None):
    system_prompt = """
あなたは VERITAS OS の Reason モジュールです。
以下の情報を踏まえ、なぜこの decision が妥当なのかを
論理的に説明してください。
"""

    user_prompt = f"""
# Query
{query}

# Planner
{planner}

# Values
{values}

# Gate
{gate}

# Context
{context}

上記を踏まえて「理由(Reason)」を日本語で簡潔に書いてください。
"""

    # ★ llm_client.chat を呼び出す
    llm_res = llm_client.chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        # extra_messages=None,  # 必要ならここに追加
        temperature=0.3,
        max_tokens=800,
    )

    # chat() は {"text": "...", "source": "..."} を返す想定
    text = llm_res.get("text", "")

    return {
        "text": text,
        "source": llm_res.get("source", "openai_llm"),
    }
