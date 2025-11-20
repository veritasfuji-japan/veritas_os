# veritas_os/core/kernel.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List

from . import adapt              # persona 学習
from . import evidence as evos   # いまは未使用だが将来のために残す
from . import debate             # Multi-Agent ReasonOS (DebateOS)
from . import world as world_model       # ★ WorldModel / world.simulate / inject_state_into_context
from . import planner as planner_core    # ★ code_change_plan 用
from veritas_os.tools import call_tool   # env tools ラッパ用
from . import agi_goals                  # ★ AGIゴール自己調整モジュール

# ============================================================
# 環境ツールラッパ（web_search / github_search）
# ============================================================

def run_env_tool(kind: str, **kwargs) -> dict:
    """
    VERITAS から外部環境ツール(web_search / github_search など)を叩く薄いラッパー。
    decide 内では **必ずこの関数経由** で呼ぶ。
    """
    try:
        return call_tool(kind, **kwargs)
    except Exception as e:
        return {
            "ok": False,
            "results": [],
            "error": f"env_tool error: {repr(e)[:200]}",
        }


# ============================================================
# ユーティリティ
# ============================================================

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _tokens(s: str) -> List[str]:
    s = (s or "").replace("　", " ").lower()
    return [t for t in s.split() if t]


def _to_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("title", "text", "description", "prompt"):
            if k in x and isinstance(x[k], str):
                return x[k]
    return str(x)


def _mk_option(title: str, description: str = "", _id: str | None = None) -> Dict[str, Any]:
    return {
        "id": _id or uuid.uuid4().hex,
        "title": title,
        "description": description,
        "score": 1.0,
    }


def _detect_intent(q: str) -> str:
    q = (q or "").strip().lower()
    rules = {
        "weather": r"(天気|気温|降水|雨|晴れ|weather|forecast)",
        "health": r"(疲れ|だる|体調|休む|回復|睡眠|寝|サウナ)",
        "learn": r"(とは|仕組み|なぜ|how|why|教えて|違い|比較)",
        "plan": r"(計画|進め|やるべき|todo|最小ステップ|スケジュール|plan)",
    }
    for name, pat in rules.items():
        if re.search(pat, q):
            return name
    return "plan"


def _gen_options_by_intent(intent: str) -> List[Dict[str, Any]]:
    if intent == "weather":
        return [
            _mk_option("天気アプリ/サイトで明日の予報を確認する"),
            _mk_option("降水確率が高い時間にリマインドを設定する"),
            _mk_option("傘・レインウェア・防水靴を準備する"),
        ]
    if intent == "health":
        return [
            _mk_option("今日は休息し回復を最優先にする"),
            _mk_option("15分の軽い散歩で血流を上げる"),
            _mk_option("短時間サウナ＋十分な水分補給を行う"),
        ]
    if intent == "learn":
        return [
            _mk_option("一次情報（公式/論文）を調べる"),
            _mk_option("要点を3行に要約する"),
            _mk_option("学んだことを1つだけ行動に落とす"),
        ]
    return [
        _mk_option("最小ステップで前進する"),
        _mk_option("情報収集を優先する"),
        _mk_option("今日は休息し回復に充てる"),
    ]


def _dedupe_alts(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    alternatives の重複を減らす:
      - title + description が同じものは1つにまとめる
      - title == 'None' や空のものは落とす
    """
    if not alts:
        return alts

    cleaned: List[Dict[str, Any]] = []
    for d in alts:
        if not isinstance(d, dict):
            continue

        title = (d.get("title") or "").strip()
        desc = (d.get("description") or "").strip()

        # タイトルが None や空
        if title.lower() == "none":
            if desc:
                title = desc[:40]
            else:
                continue  # 完全な空は削除

        if not title and desc:
            title = desc[:40]
        elif not title:
            continue

        d["title"] = title
        d["description"] = desc
        cleaned.append(d)

    # title + description のペアで重複を削除（score が高いものを残す）
    best: Dict[tuple, Dict[str, Any]] = {}
    for d in cleaned:
        key = (d["title"], d["description"])
        score = float(d.get("score", 0))

        prev = best.get(key)
        if prev is None or score > float(prev.get("score", 0)):
            best[key] = d

    # 順番を維持して返す
    result = []
    seen = set()
    for d in cleaned:
        key = (d["title"], d["description"])
        if key in seen:
            continue
        result.append(best[key])
        seen.add(key)

    return result


def _score_alternatives(
    intent: str,
    q: str,
    alts: List[Dict[str, Any]],
    telos_score: float,
    stakes: float,
    persona_bias: Dict[str, float] | None,
) -> None:
    ql = (q or "").lower()
    bias = persona_bias or {}

    def _kw_hit(title: str, kws: List[str]) -> bool:
        t = (title or "").lower()
        return any(k in t for k in kws)

    for a in alts:
        base = _safe_float(a.get("score"), 1.0)
        title = a.get("title", "") or ""

        # 目的適合の軽加点
        if intent == "weather" and _kw_hit(title, ["予報", "降水", "傘", "天気"]):
            base += 0.4
        elif intent == "health" and _kw_hit(title, ["休息", "回復", "散歩", "サウナ", "睡眠"]):
            base += 0.4
        elif intent == "learn" and _kw_hit(title, ["一次情報", "要約", "行動"]):
            base += 0.35
        elif intent == "plan" and _kw_hit(title, ["最小", "情報収集", "休息", "リファクタ", "テスト"]):
            base += 0.3

        # 直接キーワード
        if any(k in ql for k in ["雨", "降水", "umbrella", "forecast"]) and "傘" in title:
            base += 0.2

        # stakes 高い→慎重（休息/情報収集に +0.2）
        if stakes >= 0.7 and _kw_hit(title, ["休息", "回復", "情報"]):
            base += 0.2

        # ★ 学習バイアス（タイトル一致・部分一致・id一致）
        by_title = bias.get(title.lower(), 0.0)
        by_fuzzy = adapt.fuzzy_bias_lookup(bias, title)
        by_id = bias.get(f"@id:{a.get('id')}", 0.0)
        bias_boost = max(by_title, by_fuzzy, by_id)  # 最大を採用
        base *= (1.0 + 0.3 * bias_boost)  # 最大 +30%

        # Telos 係数（0.9〜1.1倍）
        base *= (0.9 + 0.2 * max(0.0, min(1.0, telos_score)))

        a["score_raw"] = _safe_float(a.get("score"), 1.0)
        a["score"] = round(base, 4)


# ============================================================
# decide 本体
# ============================================================

async def decide(
    context: Dict[str, Any],
    query: str,
    alternatives: List[Dict[str, Any]] | None,
    min_evidence: int = 1,
) -> Dict[str, Any]:
    """
    VERITAS kernel.decide:
      - 意図検出
      - Persona バイアス込みのローカルスコアリング
      - Multi-Agent DebateOS による再評価
      - WorldModel（world.simulate）による「一手先の世界予測」
      - mode=="code_change_plan" のときは bench/world/doctor からコード変更タスクを生成し、
        「どのタスクから着手するか」を DebateOS で決める
      - ★ world.inject_state_into_context により、world_state / external_knowledge を context に注入
    """
    # ---- context を安全に固める & world_state を注入 ----
    ctx_raw: Dict[str, Any] = dict(context or {})
    user_id = ctx_raw.get("user_id") or "cli"

    # ★ ここで world_state + external_knowledge を context にマージ
    ctx: Dict[str, Any] = world_model.inject_state_into_context(
        context=ctx_raw,
        user_id=user_id,
    )

    req_id = ctx.get("request_id") or uuid.uuid4().hex
    q_text = _to_text(query or ctx.get("query") or "")

    # 初期化
    evidence: List[Dict[str, Any]] = []
    critique: List[Dict[str, Any]] = []
    debate_logs: List[Dict[str, Any]] = []
    extras: Dict[str, Any] = {}

    mode = ctx.get("mode") or ""
    # Telos/重み・stakes
    tw = (ctx.get("telos_weights") or {})
    w_trans = _safe_float(tw.get("W_Transcendence", 0.6), 0.6)
    w_strug = _safe_float(tw.get("W_Struggle", 0.4), 0.4)
    telos_score = round(0.5 * w_trans + 0.5 * w_strug, 3)
    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)

    # ★ Persona（学習済みバイアス）を読み込み ＋ クリーンアップ
    persona = adapt.load_persona()
    persona_bias: Dict[str, float] = adapt.clean_bias_weights(
        dict(persona.get("bias_weights") or {})
    )

    # ★ WorldModel: 「この decision が世界にどう効きそうか」を軽く予測
    world_sim = None
    try:
        world_sim = world_model.simulate(
            user_id=user_id,
            query=q_text,
            chosen=None,  # chosen 決定前なので None。後で chosen にそのまま埋め込む。
        )
        extras["world"] = {
            "prediction": world_sim,
            "source": "world.simulate()",
        }
    except Exception as e:
        extras["world"] = {
            "error": f"world.simulate failed: {repr(e)[:80]}",
            "source": "world.simulate()",
        }

    # =======================================================
    # ★ Environment adapters (web_search / github_search)
    # =======================================================
    env_logs: Dict[str, Any] = {}
    try:
        ql = q_text.lower()

        if ctx.get("use_env_tools"):
            # フラグが立っている場合は両方走らせる
            env_logs["web_search"] = run_env_tool(
                "web_search",
                query=q_text,
                max_results=3,
            )
            env_logs["github_search"] = run_env_tool(
                "github_search",
                query=q_text,
                max_results=3,
            )
        else:
            # 軽い自動トリガー
            if "github" in ql:
                env_logs["github_search"] = run_env_tool(
                    "github_search",
                    query=q_text,
                    max_results=3,
                )
            if any(k in ql for k in ["agi", "論文", "paper", "research"]):
                env_logs["web_search"] = run_env_tool(
                    "web_search",
                    query=q_text,
                    max_results=3,
                )

    except Exception as e:
        env_logs["error"] = f"run_env_tool failed: {repr(e)[:200]}"

    if env_logs:
        extras["env_tools"] = env_logs

    # 1) intent & mode を確認
    intent = _detect_intent(q_text)

    # 2) options の初期値
    alts: List[Dict[str, Any]] = list(alternatives or [])

    # --------------------------------------------------------
    # ★ code_change_plan モード：
    #   bench_payload / world_state / doctor_report から
    #   「コード変更タスク」を生成し、それを alternatives に差し替える
    # --------------------------------------------------------
    if intent == "plan" and mode == "code_change_plan":
        bench_payload = (
            ctx.get("bench_payload")
            or ctx.get("bench")
            or {}
        )
        world_state_for_tasks = ctx.get("world_state")
        doctor_report = ctx.get("doctor_report")

        try:
            # planner.generate_code_tasks のシグネチャに合わせる
            code_plan = planner_core.generate_code_tasks(
                bench=bench_payload,
                world_state=world_state_for_tasks,
                doctor_report=doctor_report,
            )
            extras["code_change_plan"] = code_plan

            tasks = code_plan.get("tasks") or []

            alts = []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = t.get("id") or uuid.uuid4().hex
                priority = (t.get("priority") or "medium").upper()
                title = t.get("title") or "コード変更タスク"
                kind = t.get("kind") or "code_change"
                module = t.get("module") or "unknown"
                path = t.get("path") or ""

                desc_parts = [
                    f"kind={kind}",
                    f"module={module}",
                ]
                if path:
                    desc_parts.append(f"path={path}")
                if t.get("detail"):
                    desc_parts.append(f"detail={t['detail']}")

                alt = _mk_option(
                    title=f"[{priority}] {title}",
                    description=" / ".join(desc_parts),
                    _id=tid,
                )
                # 元のタスク情報も meta として保持（あとで CLI や UI から参照可）
                alt["meta"] = t
                alts.append(alt)

        except Exception as e:
            extras["code_change_plan_error"] = (
                f"generate_code_tasks failed: {repr(e)[:120]}"
            )

    # --------------------------------------------------------
    # 通常モード: 自動生成 or そのまま
    # --------------------------------------------------------
    if not alts:
        alts = _gen_options_by_intent(intent)

    # 重複をざっくり削る（LLM が似た案を量産した時のノイズ削減）
    alts = _dedupe_alts(alts)

    # 3) まずはローカルのスコアリング（学習バイアスを反映）
    _score_alternatives(intent, q_text, alts, telos_score, stakes, persona_bias)

    # 4) Multi-Agent DebateOS で再評価して最終 chosen を決定
    try:
        debate_result = debate.run_debate(
            query=q_text,
            options=alts,
            context={
                "user_id": user_id,
                "stakes": stakes,
                "telos_weights": tw,
                "mode": mode,
            },
        )

        chosen = debate_result.get("chosen") or max(
            alts, key=lambda d: _safe_float(d.get("score"), 1.0)
        )

        enriched_alts = debate_result.get("options") or alts

        extras["debate"] = {
            "raw": debate_result.get("raw"),
            "source": debate_result.get("source", "openai_llm"),
        }

        debate_logs.append(
            {
                "summary": "Multi-Agent DebateOS により候補が評価されました。",
                "risk_delta": 0.0,
                "suggested_choice_id": chosen.get("id"),
                "source": debate_result.get("source", "openai_llm"),
            }
        )

        alts = _dedupe_alts(enriched_alts)

    except Exception as e:
        chosen = max(alts, key=lambda d: _safe_float(d.get("score"), 1.0))
        debate_logs.append(
            {
                "summary": f"DebateOS フォールバック (例外: {repr(e)[:80]})",
                "risk_delta": 0.0,
                "suggested_choice_id": chosen.get("id"),
                "source": "fallback",
            }
        )

    # ★ chosen に WorldModel の予測を埋め込む（ログでも見えるように）
    if isinstance(world_sim, dict):
        chosen["world"] = world_sim

    # 5) 根拠（EvidenceOS; 外部通信なしのローカル推論）
    evidence.append(
        {
            "source": "internal:kernel",
            "uri": None,
            "snippet": f"query='{q_text}' evaluated with {len(alts)} alternatives (mode={mode})",
            "confidence": 0.8,
        }
    )

    # 6) 採択結果を履歴学習に反映（EMA）＋ AGIゴール自己調整
    try:
        # 直近履歴から bias 更新（徐々に学習）
        persona2 = adapt.update_persona_bias_from_history(window=50)

        # ついでに “今回の chosen” も強めに一票（学習レスポンスを速める）
        b = dict(persona2.get("bias_weights") or {})
        key = (chosen.get("title") or "").strip().lower() or f"@id:{chosen.get('id')}"
        if key:
            b[key] = b.get(key, 0.0) + 0.05  # ちょい足し

        # 一度クリーンアップ
        s = sum(b.values()) or 1.0
        b = {kk: vv / s for kk, vv in b.items()}
        b = adapt.clean_bias_weights(b)

        # ★ ここで AGIゴール管理モジュールによる「自己調整」を掛ける
        # world_sim の情報（progress / risk）と telos_score を使う
        world_snap: Dict[str, Any] = {}
        if isinstance(world_sim, dict):
            world_snap = dict(world_sim)

        # telos_score を暫定的に ValueEMA 的に使う
        value_ema = float(telos_score)
        fuji_risk = 0.05  # いまは固定（将来 FUJI 実装と連動させる）

        new_bias = agi_goals.auto_adjust_goals(
            bias_weights=b,
            world_snap=world_snap,
            value_ema=value_ema,
            fuji_risk=fuji_risk,
        )

        persona2["bias_weights"] = new_bias
        adapt.save_persona(persona2)

        # ログ用に今回の自己調整の状況を extras に残す
        extras.setdefault("agi_goals", {})
        extras["agi_goals"]["last_auto_adjust"] = {
            "world_progress": world_snap.get("progress")
                               or world_snap.get("predicted_progress")
                               or world_snap.get("base_progress"),
            "world_risk": world_snap.get("last_risk")
                           or world_snap.get("predicted_risk")
                           or world_snap.get("base_risk"),
            "value_ema": value_ema,
            "fuji_risk": fuji_risk,
        }

    except Exception as e:
        # 学習 or 自己調整に失敗しても推論は継続
        extras.setdefault("agi_goals", {})
        extras["agi_goals"]["error"] = repr(e)

    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": alts,
        "evidence": evidence,
        "critique": critique,
        "debate": debate_logs,
        "telos_score": telos_score,
        # ★ ここでは FUJI Gate 本体はまだ呼ばず、ステータスだけ返す
        "fuji": {"status": "allow", "reasons": [], "violations": [], "risk": 0.05},
        "rsi_note": None,
        "summary": (
            "意図検出＋学習バイアス＋Multi-Agent DebateOS＋WorldModel予測＋"
            "AGIゴール自己調整(auto_adjust_goals)＋"
            "(必要に応じて)コード変更タスク優先度評価で最適案を選定しました。"
        ),
        "description": (
            "与えられた選択肢がある場合はその中から選択し、無い場合は自動生成します。"
            "ローカル学習バイアスと Multi-Agent DebateOS により、徐々に“選択の癖”と安全性を反映します。"
            "さらに WorldModel(world_state) を用いて、『この一手が世界にどう効きそうか』を軽く予測します。"
            "AGIゴール管理モジュール(auto_adjust_goals)で、progress / risk / telos に応じてゴール重みを自己調整します。"
            "mode=code_change_plan のときは、bench/world/doctor から生成したコード変更タスク群の中から、"
            "どれに着手すべきかを優先度付きで決定します。"
        ),
        "extras": extras,
    }
