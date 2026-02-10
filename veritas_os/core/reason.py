# veritas_os/core/reason.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import llm_client

logger = logging.getLogger(__name__)

# ============================
# ログパスは「このリポジトリ内」のみを見る
# ============================

# REPO_ROOT = .../veritas_clean_test2/veritas_os
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ここでは VERITAS_LOG_DIR を無視して固定パスにする
LOG_DIR = SCRIPTS_DIR / "logs"

def _ensure_log_dir() -> None:
    """LOG_DIR を遅延的に作成する（import 時の副作用を回避）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

# Doctor / Reason 用メタログ（JSON Lines）
META_LOG = LOG_DIR / "meta_log.jsonl"


# ============================
# ① ローカル反省（数値 & メモ）
# ============================

def reflect(decision: Dict[str, Any]) -> Dict[str, Any]:
    """
    決定結果を自己評価し、次回に活かす“改善勘所”を返す。
    FUJI・Value・実効リスク・採択案の整合を点検しつつ、
    next_value_boost を -0.1〜+0.1 の範囲で必ず少しだけ動かす。
    """
    q = (decision.get("query") or "").lower()
    chosen = decision.get("chosen") or {}
    gate = decision.get("gate") or {}
    values = decision.get("values") or {}

    # ValueCore total（0〜1想定）
    v_total = float(values.get("total", 0.5))
    ema = float(values.get("ema", v_total))
    risk = float(gate.get("risk", 0.0))
    status = (gate.get("decision_status") or "allow").lower()

    tips: List[str] = []
    if risk >= 0.6:
        tips.append("高リスク：情報源を1次資料で補強")
    if ema < 0.55:
        tips.append("低価値EMA：ユーザ便益と根拠提示を強化")
    if status == "rejected":
        tips.append("拒否：代替案生成（safe-variant）を次回強制")

    # ---- “次回ブースト” を数値化（-0.1〜+0.1）----
    boost = 0.0

    # 1) ValueCore total ベース：0.5 を基準に ±0.05 まで振る
    #    v_total=0.5 → 0, v_total=1.0 → +0.05, v_total=0.0 → -0.05
    boost += (v_total - 0.5) * 0.1  # スケール 0.1 → ±0.05

    # 2) リスクが高いほど少しマイナス（0〜0.05）
    #    risk=0.0 → 0, risk=1.0 → -0.05
    boost -= risk * 0.05

    # 3) 「情報収集系」の決定はプラス方向に 0.02 上乗せ
    title = chosen.get("title") or ""
    if "情報収集" in title:
        boost += 0.02

    # 4) EMA が十分高いときはちょっとだけ前向きに（0.02）
    if ema >= 0.7:
        boost += 0.02

    # 5) クリップ（-0.1〜+0.1 に制限）
    if boost > 0.1:
        boost = 0.1
    if boost < -0.1:
        boost = -0.1

    out = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "query": q[:200],
        "chosen_title": chosen.get("title"),
        "status": status,
        "risk": round(risk, 3),
        "ema": round(ema, 3),
        "value_total": round(v_total, 3),
        "improvement_tips": tips,
        "next_value_boost": round(boost, 3),
    }

    # JSON Lines 形式で1行ずつ追記
    try:
        _ensure_log_dir()
        with open(META_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    except Exception as e:
        # ログ書き込み失敗は本体ロジックに影響させない
        logger.debug("meta_log write skipped: %s", e)

    return out


# ============================
# ② LLM による自然文 Reason 生成
# ============================

def generate_reason(
    *,
    query: str,
    planner: Dict[str, Any] | None = None,
    values: Dict[str, Any] | None = None,
    gate: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Planner / Values / Gate / Context をまとめて LLM に渡し、
    「なぜこの decision が妥当なのか」の自然文 Reason を生成する。
    """
    planner = planner or {}
    values = values or {}
    gate = gate or {}
    context = context or {}

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

    # llm_client.chat は {"text": "...", "source": "..."} を返す想定
    try:
        llm_res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=800,
        )
    except Exception as e:
        logger.error("[ReasonOS] generate_reason LLM error: %s", e)
        return {"text": "", "source": "error"}

    text = ""
    if isinstance(llm_res, dict):
        text = llm_res.get("text", "") or ""
    elif isinstance(llm_res, str):
        text = llm_res

    return {
        "text": text,
        "source": (llm_res.get("source") if isinstance(llm_res, dict) else "openai_llm"),
    }


# ============================
# ③ Self-Refine 用 テンプレ生成
# ============================

async def generate_reflection_template(
    *,
    query: str,
    chosen: Dict[str, Any],
    gate: Dict[str, Any],
    values: Dict[str, Any],
    planner: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Self-Refine / Self-Critique 的な「次回のためのテンプレ」を1つ返す。
    似たクエリが来たときに再利用できるよう、
    pattern / guidance / tags / priority を JSON で生成させる。

    失敗時は {} を返す。
    """
    if not query or not chosen:
        return {}

    system_prompt = (
        "あなたは自己改善ループを持つ AI OS『VERITAS』のメタコーチです。\n"
        "与えられたクエリ・最終決定・ゲート情報・ValueCoreスコア・プランから、\n"
        "『似た相談が次に来たとき、どのような順番で考え、どんなアクションを提案すべきか』\n"
        "をテンプレートとして1つだけ設計してください。\n\n"
        "出力は必ず JSON で、次のキーを含めてください:\n"
        "  - pattern: このテンプレが想定するクエリの特徴（日本語の短い説明）\n"
        "  - guidance: モデルへの指示文（プロンプト断片。ユーザクエリの前に付ける想定）\n"
        "  - tags: 関連タグの配列（例: [\"agi\", \"veritas\", \"roadmap\"]）\n"
        "  - priority: 0〜1 の数値（高いほど重要）\n"
    )

    user_payload = {
        "query": query,
        "chosen": chosen,
        "gate": gate,
        "values": values,
        "planner": planner or {},
    }

    try:
        # llm_client.chat は同期関数想定なので、スレッドで実行してブロックを回避
        loop = asyncio.get_running_loop()
        llm_res = await loop.run_in_executor(
            None,
            lambda: llm_client.chat(
                system_prompt=system_prompt,
                user_prompt=json.dumps(user_payload, ensure_ascii=False),
                temperature=0.2,
                max_tokens=600,
            ),
        )
    except Exception as e:
        logger.error("[ReasonOS] generate_reflection_template LLM error: %s", e)
        return {}

    text = ""
    if isinstance(llm_res, dict):
        text = llm_res.get("text", "") or ""
    elif isinstance(llm_res, str):
        text = llm_res

    if not text:
        return {}

    # LLM 出力を JSON として解釈
    try:
        data = json.loads(text)
    except Exception as e:
        logger.warning("[ReasonOS] reflection_template json parse failed: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    pattern = (data.get("pattern") or "").strip()
    guidance = (data.get("guidance") or "").strip()
    tags = data.get("tags") or []
    priority = data.get("priority", 0.5)

    if not pattern or not guidance:
        return {}

    if not isinstance(tags, list):
        tags = ["reflection"]

    try:
        priority = float(priority)
    except Exception:
        priority = 0.5

    # クリップ
    if priority < 0.0:
        priority = 0.0
    if priority > 1.0:
        priority = 1.0

    tmpl = {
        "pattern": pattern,
        "guidance": guidance,
        "tags": tags,
        "priority": priority,
    }

    # ついでに meta_log にも記録しておく（任意）
    try:
        _ensure_log_dir()
        meta = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "type": "reflection_template",
            "query": query[:200],
            "pattern": pattern,
            "priority": priority,
        }
        with open(META_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("[ReasonOS] reflection_template meta_log skipped: %s", e)

    return tmpl

