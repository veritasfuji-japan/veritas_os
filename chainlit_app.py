# chainlit_app.py
# -----------------------------------
# VERITAS v2 Chainlit デモ UI
# -----------------------------------

import logging
import os
from typing import Any, Dict, List

import chainlit as cl
import httpx

logger = logging.getLogger(__name__)


VERITAS_API_URL = os.getenv("VERITAS_API_URL", "http://localhost:8000/v1/decide")
VERITAS_API_KEY = os.getenv("VERITAS_API_KEY", "")

DEFAULT_USER_ID = os.getenv("VERITAS_USER_ID", "fujishita")


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
    chosen = res.get("chosen") or {}
    gate = res.get("gate") or {}
    values = res.get("values") or {}
    planner = res.get("planner") or res.get("plan") or {}

    title = chosen.get("title") or "決定された次の一手"
    desc = chosen.get("description") or ""

    decision_status = gate.get("decision_status") or res.get("decision_status")
    risk = gate.get("risk", 0.0)
    telos = res.get("telos_score", 0.0)

    # Planner ステップ（上位5件）
    steps = (planner.get("steps") or [])[:5]
    steps_md_lines: List[str] = []
    for i, st in enumerate(steps, 1):
        st_title = st.get("title") or st.get("name") or f"Step {i}"
        st_detail = st.get("detail") or st.get("description") or ""
        steps_md_lines.append(f"{i}. **{st_title}** - {st_detail}")

    steps_md = "\n".join(steps_md_lines) if steps_md_lines else "_まだ具体的なステップは生成されていません_"

    total_value = float(values.get("total", 0.0))
    ema = values.get("ema", None)

    value_line = f"ValueCore: total={total_value:.3f}"
    if isinstance(ema, (int, float)):
        value_line += f" / ema={ema:.3f}"

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
    extras = res.get("extras") or {}
    metrics = extras.get("metrics") or {}

    latency = metrics.get("latency_ms")
    mem_evi_cnt = metrics.get("mem_evidence_count")
    avg_u = metrics.get("avg_world_utility")
    value_ema = metrics.get("value_ema")
    eff_risk = metrics.get("effective_risk")
    telos_th = metrics.get("telos_threshold")

    lines = ["### 📊 メトリクス"]

    if latency is not None:
        lines.append(f"- 応答レイテンシ: **{int(latency)} ms**")
    if mem_evi_cnt is not None:
        lines.append(f"- Memory 由来 evidence 数: **{int(mem_evi_cnt)}**")
    if avg_u is not None:
        lines.append(f"- 平均 world.utility: **{avg_u:.3f}**")
    if value_ema is not None:
        lines.append(f"- Value EMA: **{value_ema:.3f}**")
    if eff_risk is not None:
        lines.append(f"- effective_risk: **{eff_risk:.3f}**")
    if telos_th is not None:
        lines.append(f"- telos_threshold: **{telos_th:.3f}**")

    if len(lines) == 1:
        lines.append("_メトリクス情報はまだありません_")

    return "\n".join(lines)


def format_memory_and_evidence(res: Dict[str, Any]) -> str:
    """③ Memory / Evidence 一覧"""
    extras = res.get("extras") or {}
    mem_cites = extras.get("memory_citations") or res.get("memory_citations") or []
    mem_used_count = extras.get("memory_used_count") or res.get("memory_used_count")

    evidence = res.get("evidence") or []

    # Memory 由来 evidence 抜粋
    mem_evi: List[Dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        src = str(ev.get("source", "")).lower()
        if src.startswith("memory"):
            mem_evi.append(ev)

    lines: List[str] = ["### 🧾 MemoryOS & Evidence"]

    if mem_used_count is not None:
        lines.append(f"- MemoryOS の利用件数: **{int(mem_used_count)}**")

    # memory_citations
    if mem_cites:
        lines.append("\n**Memory citations（id / kind / score）**")
        for c in mem_cites[:10]:
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
            conf = float(ev.get("confidence", 0.0))
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
    extras = res.get("extras") or {}
    env_tools = extras.get("env_tools") or {}

    web = env_tools.get("web_search") or {}
    ok = web.get("ok")
    error = (web.get("error") or "").lower()
    meta = web.get("meta") or {}
    results = web.get("results") or []

    lines: List[str] = ["### 🌐 Web Search / 外部ツール結果"]

    if not ok:
        lines.append(f"_検索エラー_: {web.get('error') or 'unknown error'}")
        return "\n".join(lines)

    # まず AGI っぽい結果だけ抽出
    agi_results: List[Dict[str, Any]] = []
    for r in results:
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
    query = message.content.strip()
    if not query:
        await cl.Message(content="空のメッセージです。何か聞いてください。").send()
        return

    # スピナー表示
    thinking = cl.Message(content="VERITAS が考えています…")
    await thinking.send()

    try:
        res = await call_veritas_decide(query)
    except Exception as e:
        # ★ L-3 修正: スタックトレースをユーザーに露出しない
        # ★ 追加修正: エラー詳細をログに記録（運用時のデバッグ用）
        logger.error("VERITAS API call failed: %r", e)
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
