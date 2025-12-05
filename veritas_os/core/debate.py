# veritas_os/core/debate.py
"""
ReasonOS Multi-Agent Debate モジュール（実用性改善版）

主な改善点:
1. 全候補却下時の degraded mode（最善候補 + 警告付き選択）
2. 却下理由の明確化と構造化
3. 段階的フォールバック（normal → degraded → safe_fallback）
4. より詳細なログとメタデータ
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import textwrap
import logging

from . import llm_client
from . import world as world_model


logger = logging.getLogger(__name__)

# 型エイリアス
DebateResult = Dict[str, Any]


# ============================
#  設定と定数
# ============================


class DebateMode:
    """Debate の動作モード"""
    NORMAL = "normal"          # 通常モード：非却下候補から選択
    DEGRADED = "degraded"      # 劣化モード：全候補却下時、最善を警告付きで選択
    SAFE_FALLBACK = "safe_fallback"  # 安全フォールバック：LLM失敗時


# スコア閾値設定
SCORE_THRESHOLDS = {
    "normal_min": 0.4,      # 通常選択の最低スコア
    "degraded_min": 0.2,    # 劣化モード最低スコア（これ以下は絶対選ばない）
    "warning_threshold": 0.6,  # これ以下は警告を付ける
}


# ============================
#  System / User プロンプト
# ============================


def _build_system_prompt() -> str:
    """
    Debate 用の system プロンプト。
    LLM に「複数エージェントになりきって」評価させる。
    """
    return textwrap.dedent("""
    あなたは「VERITAS OS」の ReasonOS / Debate モジュールです。
    以下の 4 つの役割を、あなたの内部でシミュレーションしてください：

    1. Architect（構造設計担当）
       - 各候補が、目的達成にどれだけ構造的・戦略的に有効かを評価する。

    2. Critic（批判担当）
       - 各候補の弱点・リスク・前提の甘さ・非現実性を指摘する。

    3. Safety（安全・法的・倫理チェック担当）
       - 候補が倫理的・法的に問題がないか、リスクが高すぎないかを確認する。

    4. Judge（審査担当）
       - 上記3つの観点を踏まえ、「総合スコア」を 0.0〜1.0 でつけ、
         もっとも優先すべき候補を1つ選ぶ。

    【重要な評価基準】
    - verdict は以下の3つのみ使用：
      * "採用推奨" (score 0.6以上が目安)
      * "要検討" (score 0.3-0.6が目安、リスクはあるが検討価値あり)
      * "却下" (score 0.3未満、または重大な問題あり)
    
    - 全候補を却下するのは、本当に全てが実行不可能な場合のみ
    - 少しでも前進できる候補があれば、リスクを明記した上で「要検討」を検討する

    出力フォーマットは **必ず JSON のみ** とし、次の形式に従ってください：

    {
      "options": [
        {
          "id": "step1",
          "score": 0.82,
          "score_raw": 0.82,
          "verdict": "採用推奨",
          "rejection_reason": null,
          "architect_view": "短いコメント",
          "critic_view": "短いコメント",
          "safety_view": "短いコメント",
          "summary": "総合コメント（1〜3文）"
        }
      ],
      "chosen_id": "step1"
    }

    - rejection_reason: "却下"の場合のみ、理由を簡潔に記載（"safety_risk", "infeasible", "value_conflict" など）
    - JSON 以外の文章は絶対に書かないでください。
    """)


def _build_user_prompt(
    query: str,
    options: List[Dict[str, Any]],
    context: Dict[str, Any],
    world_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Debate に渡す user プロンプトを組み立てる。
    """
    q = (query or "").strip()

    ctx_snip = json.dumps(
        {
            "user_id": context.get("user_id") or "anon",
            "stakes": context.get("stakes"),
            "telos_weights": context.get("telos_weights"),
        },
        ensure_ascii=False,
        indent=2,
    )

    opts_snip = json.dumps(options, ensure_ascii=False, indent=2)
    world_snip = json.dumps(world_snapshot or {}, ensure_ascii=False, indent=2)

    return textwrap.dedent(f"""
    # ユーザーの現在の問い / 目的

    {q}

    ---

    # 文脈情報（VERITAS コンテキスト抜粋）

    {ctx_snip}

    ---

    # WorldModel のスナップショット（必要に応じて使用）

    {world_snip}

    ---

    # 評価対象の候補一覧

    {opts_snip}

    ---

    上記の候補から、「最小ステップで前進しつつ、リスクが低く、ユーザーの長期的利益に資する」
    ものを選び、指定された JSON 形式で出力してください。
    
    【重要】全候補を却下するのは最終手段です。少しでも価値がある候補は「要検討」として残してください。
    """)


# ============================
#  共通ユーティリティ
# ============================


def _is_rejected(opt: Dict[str, Any]) -> bool:
    """verdict が「却下」系かどうかを判定。"""
    v = str(opt.get("verdict") or "").strip()
    return v in ("却下", "reject", "Rejected", "NG")


def _get_score(opt: Dict[str, Any]) -> float:
    """候補からスコアを安全に取得"""
    try:
        return float(opt.get("score") or opt.get("score_raw") or 0.0)
    except Exception:
        return 0.0


def _calc_risk_delta(
    chosen: Optional[Dict[str, Any]],
    options: List[Dict[str, Any]],
) -> float:
    """
    Debate 結果から「リスク増減（risk_delta）」を推定する。

    正方向: リスク増加（危険寄り）
    負方向: リスク減少（安全寄り）
    """
    if not chosen:
        return 0.30

    delta = 0.0

    safety_view = str(chosen.get("safety_view") or "").lower()
    critic_view = str(chosen.get("critic_view") or "").lower()
    verdict     = str(chosen.get("verdict") or "").strip()
    score = _get_score(chosen)

    # 1) safety_view 内の危険ワードで加点
    risk_keywords = {
        "危険": 0.15,
        "重大": 0.12,
        "リスク": 0.08,
        "問題": 0.05,
        "違反": 0.20,
        "禁止": 0.18,
        "illegal": 0.20,
        "ban": 0.15,
    }
    for kw, w in risk_keywords.items():
        if kw in safety_view:
            delta += w

    # 2) verdict による調整
    if verdict == "要検討":
        delta += 0.05
    elif verdict == "却下":
        delta += 0.25
    elif verdict == "採用推奨":
        if "問題なし" in safety_view or "安全" in safety_view:
            delta -= 0.05

    # 3) score が低いほど不安
    if score < 0.5:
        delta += (0.5 - score) * 0.2
    elif score > 0.8:
        if "問題" not in safety_view and "危険" not in safety_view:
            delta -= (score - 0.8) * 0.05

    # 4) critic_view に強い否定があれば追加
    if any(w in critic_view for w in ["致命", "深刻", "重大", "critical"]):
        delta += 0.10

    delta = max(-0.30, min(0.50, delta))
    return round(delta, 3)


def _build_debate_summary(
    chosen: Optional[Dict[str, Any]],
    options: List[Dict[str, Any]],
    mode: str,
) -> Dict[str, Any]:
    """モニタリング・デバッグ用の詳細サマリ"""
    total = len(options)
    rejected_count = len([o for o in options if _is_rejected(o)])
    
    scores = [_get_score(o) for o in options]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    min_score = min(scores) if scores else 0.0

    return {
        "total_options": total,
        "rejected_count": rejected_count,
        "accepted_count": total - rejected_count,
        "mode": mode,
        "chosen_score": _get_score(chosen) if chosen else 0.0,
        "chosen_verdict": (chosen or {}).get("verdict"),
        "avg_score": round(avg_score, 3),
        "max_score": round(max_score, 3),
        "min_score": round(min_score, 3),
        "source": "debate.v2_improved",
    }


def _create_warning_message(
    chosen: Dict[str, Any],
    mode: str,
    all_rejected: bool,
) -> str:
    """警告メッセージを生成"""
    score = _get_score(chosen)
    verdict = chosen.get("verdict", "")
    
    warnings = []
    
    if mode == DebateMode.DEGRADED:
        warnings.append("⚠️ 全候補が通常基準を満たしませんでした")
        warnings.append(f"最もスコアの高い候補（{score:.2f}）を選択しましたが、慎重な検討が必要です")
    
    if score < SCORE_THRESHOLDS["warning_threshold"]:
        warnings.append(f"⚠️ 選択候補のスコアが低めです（{score:.2f}）")
    
    if verdict == "却下":
        warnings.append("⚠️ この候補は本来却下対象ですが、他に選択肢がありません")
    elif verdict == "要検討":
        warnings.append("ℹ️ この候補にはリスクがあります。実行前に詳細を確認してください")
    
    safety_view = str(chosen.get("safety_view") or "")
    if any(kw in safety_view for kw in ["危険", "リスク", "問題", "違反"]):
        warnings.append(f"⚠️ 安全性の懸念: {chosen.get('safety_view', '')}")
    
    return "\n".join(warnings) if warnings else ""


# ============================
#  JSON パース
# ============================


def _safe_parse(raw: str) -> Dict[str, Any]:
    """LLM 出力から JSON を安全に取り出す"""
    if not raw:
        return {"options": [], "chosen_id": None}

    cleaned = raw.strip()

    # ```json ... ``` 除去
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    def _wrap(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"options": obj, "chosen_id": None}
        return {"options": [], "chosen_id": None}

    # 1) そのままパース
    try:
        obj = json.loads(cleaned)
        return _wrap(obj)
    except Exception:
        pass

    # 2) {} を抜き出して再トライ
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        snippet = cleaned[start:end]
        obj = json.loads(snippet)
        return _wrap(obj)
    except Exception:
        return {"options": [], "chosen_id": None}


# ============================
#  選択ロジック（改善版）
# ============================


def _select_best_candidate(
    enriched_list: List[Dict[str, Any]],
    min_score: float,
    allow_rejected: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    指定条件で最良の候補を選択
    
    Args:
        enriched_list: 評価済み候補リスト
        min_score: 最低スコア閾値
        allow_rejected: 却下候補も許可するか
    """
    candidates = enriched_list
    
    if not allow_rejected:
        candidates = [o for o in enriched_list if not _is_rejected(o)]
    
    # スコアフィルタリング
    candidates = [o for o in candidates if _get_score(o) >= min_score]
    
    if not candidates:
        return None
    
    # 最高スコアを選択
    best = max(candidates, key=lambda o: _get_score(o))
    return best


def _create_degraded_choice(
    enriched_list: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    全候補却下時の degraded mode 選択
    
    戦略:
    1. スコア 0.2 以上の中から最善を選ぶ
    2. それでもなければ、却下候補含めて最善を選ぶ
    3. 警告メッセージを付与
    """
    # 戦略1: 却下だがスコアが最低限ある候補
    degraded_min = SCORE_THRESHOLDS["degraded_min"]
    candidate = _select_best_candidate(
        enriched_list,
        min_score=degraded_min,
        allow_rejected=True
    )
    
    if candidate:
        logger.warning(
            f"DebateOS: Degraded mode - 選択候補 '{candidate.get('title')}' "
            f"(score: {_get_score(candidate):.2f}, verdict: {candidate.get('verdict')})"
        )
        return candidate
    
    # 戦略2: スコアに関わらず最善
    if enriched_list:
        candidate = max(enriched_list, key=lambda o: _get_score(o))
        logger.warning(
            f"DebateOS: Emergency fallback - 最低基準未満ですが選択: "
            f"'{candidate.get('title')}' (score: {_get_score(candidate):.2f})"
        )
        return candidate
    
    return None


# ============================
#  フォールバック
# ============================


def _fallback_debate(
    options: List[Dict[str, Any]]
) -> DebateResult:
    """
    LLM 失敗時の安全フォールバック
    """
    if not options:
        return {
            "options": [],
            "chosen": None,
            "raw": None,
            "source": DebateMode.SAFE_FALLBACK,
            "mode": DebateMode.SAFE_FALLBACK,
            "risk_delta": 0.30,
            "warnings": ["⚠️ 候補が存在しないため選択できません"],
            "debate_summary": {
                "total_options": 0,
                "rejected_count": 0,
                "accepted_count": 0,
                "mode": DebateMode.SAFE_FALLBACK,
                "chosen_score": 0.0,
                "chosen_verdict": None,
                "source": "debate.v2_improved",
            },
        }

    enriched: List[Dict[str, Any]] = []
    for opt in options:
        o = dict(opt)
        o.setdefault("id", o.get("id") or o.get("title") or "opt")
        o["score"] = 0.5
        o["score_raw"] = 0.5
        o["verdict"] = "要検討"
        o["rejection_reason"] = None
        o["architect_view"] = "フォールバック: Architect 評価なし"
        o["critic_view"] = "フォールバック: Critic 評価なし"
        o["safety_view"] = "フォールバック: Safety 評価なし"
        o["summary"] = "LLM 失敗により、最初の候補を暫定選択。"
        enriched.append(o)

    chosen = enriched[0]
    risk_delta = _calc_risk_delta(chosen, enriched)
    summary = _build_debate_summary(chosen, enriched, DebateMode.SAFE_FALLBACK)
    
    warning = _create_warning_message(chosen, DebateMode.SAFE_FALLBACK, False)
    warning = "⚠️ LLM評価失敗により安全フォールバックを使用\n" + warning

    return {
        "options": enriched,
        "chosen": chosen,
        "raw": None,
        "source": DebateMode.SAFE_FALLBACK,
        "mode": DebateMode.SAFE_FALLBACK,
        "risk_delta": risk_delta,
        "warnings": warning.split("\n") if warning else [],
        "debate_summary": summary,
    }


# ============================
#  メイン入口（改善版）
# ============================


def run_debate(
    query: str,
    options: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> DebateResult:
    """
    ReasonOS から呼び出すメイン入口（実用性改善版）

    主な改善:
    - 全候補却下時に degraded mode で最善候補を選択
    - 明確な警告メッセージ
    - より詳細なログとメタデータ

    入力:
      - query: decide に渡された元クエリ
      - options: Planner や MemoryOS などから集めた候補一覧
      - context: stakes / telos_weights / user_id など

    戻り値:
    {
      "chosen": {...},
      "options": [...],
      "raw": {...},
      "source": "openai_llm",
      "mode": "normal" | "degraded" | "safe_fallback",
      "risk_delta": float,
      "warnings": [str, ...],
      "debate_summary": {...}
    }
    """
    ctx = dict(context or {})

    # WorldModel スナップショット
    try:
        world_snap = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = {}

    if not options:
        logger.warning("DebateOS: No options provided")
        return _fallback_debate(options)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, options, ctx, world_snap)

    try:
        # LLM 呼び出し
        res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_messages=None,
            temperature=0.25,
            max_tokens=1000,
        )
        raw_text = res.get("text") if isinstance(res, dict) else str(res)
        parsed = _safe_parse(raw_text)

        out_opts = parsed.get("options") or []
        chosen_id = parsed.get("chosen_id")

        # 入力 options をベースに enriched dict を構築
        enriched_by_id: Dict[str, Dict[str, Any]] = {}
        for base in options:
            bid = base.get("id") or base.get("title") or "opt"
            base_copy = dict(base)
            base_copy.setdefault("id", bid)
            enriched_by_id[bid] = base_copy

        # LLM 評価結果をマージ
        for o in out_opts:
            if not isinstance(o, dict):
                continue
            oid = o.get("id")
            if not oid or oid not in enriched_by_id:
                continue
            target = enriched_by_id[oid]
            for k, v in o.items():
                target[k] = v

        enriched_list = list(enriched_by_id.values())

        # ============================
        # 選択ロジック（3段階フォールバック）
        # ============================
        
        chosen: Optional[Dict[str, Any]] = None
        mode = DebateMode.NORMAL
        all_rejected = False

        # 【フェーズ1】通常モード: 非却下 & スコア閾値以上
        non_rejected = [o for o in enriched_list if not _is_rejected(o)]
        
        if non_rejected:
            # LLM が chosen_id を指定していればそれを優先（ただし却下でないこと）
            if chosen_id and chosen_id in enriched_by_id:
                cand = enriched_by_id[chosen_id]
                if not _is_rejected(cand) and _get_score(cand) >= SCORE_THRESHOLDS["normal_min"]:
                    chosen = cand
            
            # chosen_id がダメなら最高スコアを選択
            if chosen is None:
                chosen = _select_best_candidate(
                    non_rejected,
                    min_score=SCORE_THRESHOLDS["normal_min"],
                    allow_rejected=False
                )
        
        # 【フェーズ2】Degraded モード: 全候補却下時
        if chosen is None:
            logger.warning("DebateOS: All candidates rejected or below threshold, entering degraded mode")
            all_rejected = True
            mode = DebateMode.DEGRADED
            chosen = _create_degraded_choice(enriched_list)
        
        # 【フェーズ3】最終フォールバック
        if chosen is None:
            logger.error("DebateOS: Failed to select any candidate, using safe fallback")
            return _fallback_debate(options)

        # ============================
        # 結果の組み立て
        # ============================
        
        risk_delta = _calc_risk_delta(chosen, enriched_list)
        summary = _build_debate_summary(chosen, enriched_list, mode)
        warning_msg = _create_warning_message(chosen, mode, all_rejected)
        warnings = [w for w in warning_msg.split("\n") if w.strip()]

        # ログ出力
        if mode == DebateMode.NORMAL:
            logger.info(
                f"DebateOS: Selected '{chosen.get('title')}' "
                f"(score: {_get_score(chosen):.2f}, verdict: {chosen.get('verdict')})"
            )
        else:
            logger.warning(
                f"DebateOS: Degraded selection '{chosen.get('title')}' "
                f"(score: {_get_score(chosen):.2f}, verdict: {chosen.get('verdict')})"
            )

        return {
            "chosen": chosen,
            "options": enriched_list,
            "raw": parsed,
            "source": "openai_llm",
            "mode": mode,
            "risk_delta": risk_delta,
            "warnings": warnings,
            "debate_summary": summary,
        }

    except Exception as e:
        logger.error(f"DebateOS: LLM call failed: {e}")
        return _fallback_debate(options)

