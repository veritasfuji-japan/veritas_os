# chainlit_app.py
# -----------------------------------
# VERITAS v2 Chainlit デモ UI
# -----------------------------------

import logging
import math
import os
import re
from typing import Any, Dict, List, Optional

import chainlit as cl
import httpx

logger = logging.getLogger(__name__)


VERITAS_API_URL = os.getenv("VERITAS_API_URL", "http://localhost:8000/v1/decide")
VERITAS_API_KEY = os.getenv("VERITAS_API_KEY", "")

DEFAULT_USER_ID = os.getenv("VERITAS_USER_ID", "fujishita")


def _safe_float(value: Any) -> Optional[float]:
    """Return a float when conversion is possible, otherwise ``None``."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _safe_int(value: Any) -> Optional[int]:
    """Return an int when conversion is possible, otherwise ``None``."""
    as_float = _safe_float(value)
    if as_float is None:
        return None
    return int(as_float)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float for formatting, or a default value."""
    parsed = _safe_float(value)
    if parsed is None:
        return default
    return parsed


def _as_dict(value: Any) -> Dict[str, Any]:
    """Return a dictionary value, or an empty dict for malformed payloads."""
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> List[Any]:
    """Return a list value, or an empty list for malformed payloads."""
    if isinstance(value, list):
        return value
    return []


# --------- VERITAS API 呼び出しヘルパー ---------

async def call_veritas_decide(query: str) -> Dict[str, Any]:
    """VERITAS /v1/decide を叩いて結果 JSON を返す。"""
    headers = {"Content-Type": "application/json"}
    if VERITAS_API_KEY:
        headers["X-API-Key"] = VERITAS_API_KEY

    payload = {
        "query": query,
        "user_id": DEFAULT_USER_ID,
        "context": {
            "user_id": DEFAULT_USER_ID,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(VERITAS_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


# ========= 表示用フォーマッタ =========

def format_main_answer(res: Dict[str, Any]) -> str:
    """① メインの回答エリア（人間が一番見るところ）"""
    chosen = _as_dict(res.get("chosen"))
    gate = _as_dict(res.get("gate"))
    values = _as_dict(res.get("values"))
    planner = _as_dict(res.get("planner") or res.get("plan"))

    title = chosen.get("title") or "決定された次の一手"
    desc = chosen.get("description") or ""

    decision_status = gate.get("decision_status") or res.get("decision_status")
    risk = _coerce_float(gate.get("risk"), default=0.0)
    telos = _coerce_float(res.get("telos_score"), default=0.0)

    # Planner ステップ（上位5件）
    steps = _as_list(planner.get("steps"))[:5]
    steps_md_lines: List[str] = []
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            continue
        st_title = st.get("title") or st.get("name") or f"Step {i}"
        st_detail = st.get("detail") or st.get("description") or ""
        steps_md_lines.append(f"{i}. **{st_title}** - {st_detail}")

    steps_md = "\n".join(steps_md_lines) if steps_md_lines else "_まだ具体的なステップは生成されていません_"

    total_value = _safe_float(values.get("total"))
    if total_value is None:
        total_value = 0.0
    ema = values.get("ema", None)
    ema_float = _safe_float(ema)

    value_line = f"ValueCore: total={total_value:.3f}"
    if ema_float is not None:
        value_line += f" / ema={ema_float:.3f}"

    md = f"""### 🧠 VERITAS の決定

**結論（chosen）**  
> {title}

{desc or '_説明はありません_'}  

---

**ゲート・スコア**

- 決定ステータス: **{decision_status}**
- FUJIリスク: **{risk:.3f}**
- Telosスコア: **{telos:.3f}**
- {value_line}

---

### ✅ この後のステップ（Planner 抜粋）

{steps_md}
"""
    return md


def format_metrics(res: Dict[str, Any]) -> str:
    """② メトリクス（latency等）"""
    extras = _as_dict(res.get("extras"))
    metrics = _as_dict(extras.get("metrics"))

    latency = metrics.get("latency_ms")
    mem_evi_cnt = metrics.get("mem_evidence_count")
    avg_u = metrics.get("avg_world_utility")
    value_ema = metrics.get("value_ema")
    eff_risk = metrics.get("effective_risk")
    telos_th = metrics.get("telos_threshold")

    lines = ["### 📊 メトリクス"]

    latency_int = _safe_int(latency)
    mem_evi_count_int = _safe_int(mem_evi_cnt)
    avg_u_float = _safe_float(avg_u)
    value_ema_float = _safe_float(value_ema)
    eff_risk_float = _safe_float(eff_risk)
    telos_th_float = _safe_float(telos_th)

    if latency_int is not None:
        lines.append(f"- 応答レイテンシ: **{latency_int} ms**")
    if mem_evi_count_int is not None:
        lines.append(f"- Memory 由来 evidence 数: **{mem_evi_count_int}**")
    if avg_u_float is not None:
        lines.append(f"- 平均 world.utility: **{avg_u_float:.3f}**")
    if value_ema_float is not None:
        lines.append(f"- Value EMA: **{value_ema_float:.3f}**")
    if eff_risk_float is not None:
        lines.append(f"- effective_risk: **{eff_risk_float:.3f}**")
    if telos_th_float is not None:
        lines.append(f"- telos_threshold: **{telos_th_float:.3f}**")

    if len(lines) == 1:
        lines.append("_メトリクス情報はまだありません_")

    return "\n".join(lines)


def format_memory_and_evidence(res: Dict[str, Any]) -> str:
    """③ Memory / Evidence 一覧"""
    extras = _as_dict(res.get("extras"))
    mem_cites = _as_list(extras.get("memory_citations") or res.get("memory_citations"))
    mem_used_count = extras.get("memory_used_count") or res.get("memory_used_count")

    evidence = _as_list(res.get("evidence"))

    # Memory 由来 evidence 抜粋
    mem_evi: List[Dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        src = str(ev.get("source", "")).lower()
        if src.startswith("memory"):
            mem_evi.append(ev)

    lines: List[str] = ["### 🧾 MemoryOS & Evidence"]

    mem_used_count_int = _safe_int(mem_used_count)
    if mem_used_count_int is not None:
        lines.append(f"- MemoryOS の利用件数: **{mem_used_count_int}**")

    # memory_citations
    if mem_cites:
        lines.append("\n**Memory citations（id / kind / score）**")
        for c in mem_cites[:10]:
            if not isinstance(c, dict):
                continue
            cid = c.get("id")
            kind = c.get("kind")
            score = c.get("score")
            lines.append(f"- `{cid}` | kind={kind} | score={score}")

    # memory evidence snippets
    if mem_evi:
        lines.append("\n**Memory 由来 evidence（最大5件）**")
        for ev in mem_evi[:5]:
            src = ev.get("source")
            snip = ev.get("snippet") or ""
            conf = _safe_float(ev.get("confidence"))
            if conf is None:
                conf = 0.0
            if len(snip) > 160:
                snip = snip[:157] + "..."
            lines.append(f"- ({src}, conf={conf:.2f}) {snip}")
    else:
        lines.append("\n_今回は Memory 由来 evidence は利用されていません（または0件です）_")

    return "\n".join(lines)


# ---- Web Search 用ヘルパ ----

def _is_agi_like_text(text: str) -> bool:
    """タイトル＋スニペットが AGI 関連かどうかの簡易判定"""
    t = (text or "").lower()
    if "artificial general intelligence" in t:
        return True
    if "general-purpose ai" in t or "general purpose ai" in t:
        return True
    # agi という単語単体（会社名の agl などは除外）
    if " agi " in t or t.startswith("agi ") or " agi," in t or " agi." in t:
        return True
    return False


def format_web_results(res: Dict[str, Any]) -> str:
    """④ Web Search / 外部ツール結果（AGI っぽいものだけ表示）"""
    extras = _as_dict(res.get("extras"))
    env_tools = _as_dict(extras.get("env_tools"))

    web = _as_dict(env_tools.get("web_search"))
    ok = web.get("ok")
    error = (web.get("error") or "").lower()
    meta = _as_dict(web.get("meta"))
    results = _as_list(web.get("results"))

    lines: List[str] = ["### 🌐 Web Search / 外部ツール結果"]

    if not ok:
        lines.append(f"_検索エラー_: {web.get('error') or 'unknown error'}")
        return "\n".join(lines)

    # まず AGI っぽい結果だけ抽出
    agi_results: List[Dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        title = r.get("title") or ""
        snip = r.get("snippet") or ""
        if _is_agi_like_text(title + " " + snip):
            agi_results.append(r)

    agi_cnt = meta.get("agi_result_count")
    agi_filter_applied = bool(meta.get("agi_filter_applied"))

    # サーバ側で「AGI結果ゼロ」と判定済み or 自前フィルタでもゼロ → 何も出さない
    if (
        "no_agi_like_results" in error
        or (agi_filter_applied and (agi_cnt == 0 or not agi_results))
        or (not agi_results and results)
    ):
        lines.append("AGI関連と判断できる Web 検索結果は見つかりませんでした。")
        return "\n".join(lines)

    # そもそも Web Search が走ってないケース
    if not results and not agi_results:
        lines.append("_今回の decision では Web Search は利用されていません。_")
        return "\n".join(lines)

    # ここまで来たら AGI 系だけ表示
    show = agi_results or results

    for i, r in enumerate(show[:5], 1):
        title = r.get("title") or "(no title)"
        url = r.get("url") or ""
        snip = r.get("snippet") or ""
        if len(snip) > 160:
            snip = snip[:157] + "..."
        lines.append(f"{i}. **{title}**")
        if url:
            lines.append(f"   - {url}")
        if snip:
            lines.append(f"   - {snip}")

    return "\n".join(lines)


def format_reason(res: Dict[str, Any]) -> str:
    """⑤ ReasonOS（反省）"""
    reason = res.get("reason")

    # generate_reason() の新仕様に合わせる
    if isinstance(reason, dict):
        note = (
            reason.get("note")
            or reason.get("text")
            or reason.get("reason")
            or ""
        )
        next_value_boost = reason.get("next_value_boost")
        extra = []
        if next_value_boost is not None:
            extra.append(f"next_value_boost={next_value_boost}")
        extra_line = f" ({', '.join(extra)})" if extra else ""
        return f"""### 🔍 ReasonOS（反省メモ）

{note or '_テキストはありません_'}{extra_line}
"""
    elif isinstance(reason, str):
        return f"""### 🔍 ReasonOS（反省メモ）

{reason}
"""
    else:
        return "### 🔍 ReasonOS（反省メモ）\n_反省情報はありません_"


# --------- Chainlit イベント ---------

@cl.on_chat_start
async def on_chat_start():
    await cl.Message(
        content=(
            "VERITAS v2 Chainlit デモへようこそ 🎛\n\n"
            "- 下の入力欄に「今日やるべきことをAGIロードマップに沿って整理して」などと入力してください。\n"
            "- VERITAS が /v1/decide を通じて決定し、その結果・メトリクス・Memory・Web Search・Reason を分かりやすく表示します。"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    MAX_QUERY_LENGTH = 10_000
    query = message.content.strip()
    if not query:
        await cl.Message(content="空のメッセージです。何か聞いてください。").send()
        return
    if len(query) > MAX_QUERY_LENGTH:
        await cl.Message(content=f"入力が長すぎます（最大{MAX_QUERY_LENGTH}文字）。短くしてください。").send()
        return
    # Strip null bytes and control characters (except newline/tab)
    query = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)

    # スピナー表示
    thinking = cl.Message(content="VERITAS が考えています…")
    await thinking.send()

    try:
        res = await call_veritas_decide(query)
    except Exception as e:
        # ★ L-3 修正: スタックトレースをユーザーに露出しない
        # ★ 追加修正: エラー詳細をログに記録（運用時のデバッグ用）
        logger.error("VERITAS API call failed: %r (query length=%d)", e, len(query))
        thinking.content = "VERITAS API 呼び出しでエラーが発生しました。しばらくしてから再度お試しください。"
        await thinking.update()
        return

    # ① メイン回答
    main_md = format_main_answer(res)
    thinking.content = main_md
    await thinking.update()

    # ② メトリクス
    metrics_md = format_metrics(res)
    await cl.Message(content=metrics_md).send()

    # ③ Memory & Evidence
    mem_md = format_memory_and_evidence(res)
    await cl.Message(content=mem_md).send()

    # ④ Web Search / 外部ツール結果（AGI 以外は隠す）
    web_md = format_web_results(res)
    await cl.Message(content=web_md).send()

    # ⑤ ReasonOS（反省）
    reason_md = format_reason(res)
    await cl.Message(content=reason_md).send()
