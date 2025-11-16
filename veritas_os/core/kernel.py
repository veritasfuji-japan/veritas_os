# veritas/core/kernel.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re, uuid
from typing import Any, Dict, List
from . import adapt  # persona 学習
from . import evidence as evos  # いまは未使用だが将来のために残す


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
        "plan": r"(計画|進め|やるべき|todo|最小ステップ|スケジュール)",
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
        elif intent == "plan" and _kw_hit(title, ["最小", "情報収集", "休息"]):
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


async def decide(
    context: Dict[str, Any],
    query: str,
    alternatives: List[Dict[str, Any]] | None,
    min_evidence: int = 1,
) -> Dict[str, Any]:
    # ---- context を安全に固める ----
    ctx: Dict[str, Any] = dict(context or {})
    req_id = ctx.get("request_id") or uuid.uuid4().hex
    q_text = _to_text(query or ctx.get("query") or "")

    # 初期化
    evidence: List[Dict[str, Any]] = []
    critique: List[Dict[str, Any]] = []
    debate: List[Dict[str, Any]] = []
    extras: Dict[str, Any] = {}

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

    # 1) options 無ければ自動生成（ある場合は“その中から”）
    alts: List[Dict[str, Any]] = list(alternatives or [])
    if not alts:
        intent = _detect_intent(q_text)
        alts = _gen_options_by_intent(intent)
    else:
        intent = _detect_intent(q_text)

    # 2) スコアリング（学習バイアスを反映）
    _score_alternatives(intent, q_text, alts, telos_score, stakes, persona_bias)

    # 3) 採択
    chosen = max(alts, key=lambda d: _safe_float(d.get("score"), 1.0))

    # 4) 根拠（EvidenceOS; 外部通信なしのローカル推論）
    evidence.append(
        {
            "source": "internal:kernel",
            "uri": None,
            "snippet": f"query='{q_text}' evaluated with {len(alts)} alternatives",
            "confidence": 0.8,
        }
    )

    # 5) 採択結果を履歴学習に反映（EMA）：trust_log.jsonl を主に学習
    try:
        # 直近履歴から bias 更新（徐々に学習）
        persona2 = adapt.update_persona_bias_from_history(window=50)

        # ついでに “今回の chosen” も強めに一票（学習レスポンスを速める）
        b = dict(persona2.get("bias_weights") or {})
        key = (chosen.get("title") or "").strip().lower() or f"@id:{chosen.get('id')}"
        if key:
            b[key] = b.get(key, 0.0) + 0.05  # ちょい足し
            # 再正規化＋クリーニング
            s = sum(b.values()) or 1.0
            b = {kk: vv / s for kk, vv in b.items()}
            persona2["bias_weights"] = adapt.clean_bias_weights(b)
            adapt.save_persona(persona2)
    except Exception:
        # 学習に失敗しても推論は継続
        pass

    return {
        "request_id": req_id,
        "chosen": chosen,
        "alternatives": alts,
        "evidence": evidence,
        "critique": critique,
        "debate": debate,
        "telos_score": telos_score,
        "fuji": {"status": "allow", "reasons": [], "violations": []},
        "rsi_note": None,
        "summary": "意図検出＋学習バイアスで最適案を選定しました。",
        "description": "与えられた選択肢がある場合はその中から選択、無い場合は自動生成します。学習バイアスで次第に“選択の癖”を反映します。",
    }
