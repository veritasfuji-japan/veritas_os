# veritas_os/core/debate.py
"""
ReasonOS Multi-Agent Debate モジュール（強化MVP版）

役割:
- Planner が生成した options (steps) や過去の action 候補に対して、
  「複数の視点（Architect / Critic / Safety / Judge）」で評価を行い、
  最終的な chosen を決める。

前提:
- options は {id, title, description(or detail)} を持つ dict のリスト
- llm_client.chat() が利用可能
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import textwrap

from . import llm_client
from . import world as world_model


# 型エイリアス
DebateResult = Dict[str, Any]


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

    出力フォーマットは **必ず JSON のみ** とし、次の形式に従ってください：

    {
      "options": [
        {
          "id": "step1",             // 入力で渡された id をそのまま使う
          "score": 0.82,             // 0.0〜1.0 の総合スコア
          "score_raw": 0.82,         // 同じ値でよい（互換用）
          "verdict": "採用推奨",       // "採用推奨" / "要検討" / "却下" のいずれか
          "architect_view": "短いコメント",
          "critic_view": "短いコメント",
          "safety_view": "短いコメント",
          "summary": "総合コメント（1〜3文）"
        }
      ],
      "chosen_id": "step1"
    }

    - JSON 以外の文章は絶対に書かないでください。
    - options の並び順は入力と同じでも、ソートしても構いません。
    - score は相対評価で構いませんが、最も良い候補は 0.7〜1.0 の範囲にしてください。
    """)


def _build_user_prompt(
    query: str,
    options: List[Dict[str, Any]],
    context: Dict[str, Any],
    world_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Debate に渡す user プロンプトを組み立てる。
    - query: ユーザーの元の問い
    - options: Planner + その他候補で構成された一覧
    - context: stakes, telos_weights, user_id など
    - world_snapshot: world.snapshot("veritas_agi") 等
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
    """)


# ============================
#  共通ユーティリティ
# ============================


def _is_rejected(opt: Dict[str, Any]) -> bool:
    """verdict が「却下」系かどうかを判定。"""
    v = str(opt.get("verdict") or "").strip()
    return v in ("却下", "reject", "Rejected", "NG")


def _calc_risk_delta(
    chosen: Optional[Dict[str, Any]],
    options: List[Dict[str, Any]],
) -> float:
    """
    Debate 結果から「リスク増減（risk_delta）」を推定する。

    正方向: リスク増加（危険寄り）
    負方向: リスク減少（安全寄り）

    FUJI 側のリスクスコアに加算されることを前提とした値なので、
    -0.30〜+0.50 程度にクリップしておく。
    """
    # 何も選べなかった場合は「全体的に不安」扱いでやや危険寄り
    if not chosen:
        return 0.30

    delta = 0.0

    safety_view = str(chosen.get("safety_view") or "").lower()
    critic_view = str(chosen.get("critic_view") or "").lower()
    verdict     = str(chosen.get("verdict") or "").strip()
    try:
        score = float(chosen.get("score") or chosen.get("score_raw") or 0.5)
    except Exception:
        score = 0.5

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
        # 安全寄りなら少しだけマイナス方向もあり得る
        if "問題なし" in safety_view or "安全" in safety_view:
            delta -= 0.05

    # 3) score が低いほど不安 → 少しリスク増
    if score < 0.5:
        delta += (0.5 - score) * 0.2
    elif score > 0.8:
        # 自信が高く、他にリスク要因がなければわずかにリスク減
        if "問題" not in safety_view and "危険" not in safety_view:
            delta -= (score - 0.8) * 0.05

    # 4) critic_view に強い否定があれば追加加点
    if any(w in critic_view for w in ["致命", "深刻", "重大", "critical"]):
        delta += 0.10

    # 上限・下限 clip
    delta = max(-0.30, min(0.50, delta))
    return round(delta, 3)


def _build_debate_summary(
    chosen: Optional[Dict[str, Any]],
    options: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """モニタリング・デバッグ用の簡易サマリ."""
    total = len(options)
    rejected_count = len([o for o in options if _is_rejected(o)])

    try:
        chosen_score = float(
            (chosen or {}).get("score") or (chosen or {}).get("score_raw") or 0.0
        )
    except Exception:
        chosen_score = 0.0

    return {
        "total_options": total,
        "rejected_count": rejected_count,
        "chosen_score": chosen_score,
        "chosen_verdict": (chosen or {}).get("verdict"),
        "source": "debate.v1",
    }


# ============================
#  JSON パースまわり（強化版）
# ============================


def _safe_parse(raw: str) -> Dict[str, Any]:
    """
    LLM 出力から JSON を安全に取り出すユーティリティ。

    - Markdown の ```json / ``` コードブロックが付いていても処理する
    - トップレベルが配列だけの場合は {"options": [...]} にラップする
    - ダメな場合は最小構造で返す
    """
    if not raw:
        return {"options": [], "chosen_id": None}

    cleaned = raw.strip()

    # ```json ... ``` のようなコードブロックを除去
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

    # 2) 先頭の '{' 〜 最後の '}' を抜き出して再トライ
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        snippet = cleaned[start:end]
        obj = json.loads(snippet)
        return _wrap(obj)
    except Exception:
        return {"options": [], "chosen_id": None}


# ============================
#  フォールバック Debate
# ============================


def _fallback_debate(
    options: List[Dict[str, Any]]
) -> DebateResult:
    """
    LLM が壊れたときのフォールバック：
    - とりあえず最初の候補を選ぶ
    - score は全部 0.5 にしておく
    """
    if not options:
        return {
            "options": [],
            "chosen": None,
            "raw": None,
            "source": "fallback",
            "risk_delta": 0.30,  # 「判断不能 = やや危険寄り」扱い
            "debate_summary": {
                "total_options": 0,
                "rejected_count": 0,
                "chosen_score": 0.0,
                "chosen_verdict": None,
                "source": "debate.v1",
            },
        }

    enriched: List[Dict[str, Any]] = []
    for opt in options:
        o = dict(opt)
        o.setdefault("id", o.get("id") or o.get("title") or "opt")
        o["score"] = 0.5
        o["score_raw"] = 0.5
        o["verdict"] = "要検討"
        o["architect_view"] = "フォールバック: Architect 評価なし"
        o["critic_view"] = "フォールバック: Critic 評価なし"
        o["safety_view"] = "フォールバック: Safety 評価なし"
        o["summary"] = "LLM 失敗により、最初の候補を暫定選択。"
        enriched.append(o)

    chosen = enriched[0]
    risk_delta = _calc_risk_delta(chosen, enriched)
    summary = _build_debate_summary(chosen, enriched)

    return {
        "options": enriched,
        "chosen": chosen,
        "raw": None,
        "source": "fallback",
        "risk_delta": risk_delta,
        "debate_summary": summary,
    }


# ============================
#  メイン入口
# ============================


def run_debate(
    query: str,
    options: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> DebateResult:
    """
    ReasonOS から呼び出すメイン入口。

    入力:
      - query: decide に渡された元クエリ（例: "veritasを活用したい"）
      - options: Planner や MemoryOS などから集めた候補一覧
      - context: stakes / telos_weights / user_id など（任意）

    戻り値:
    {
      "chosen": {...},        # enriched option (score 等付き)
      "options": [...],       # enriched options
      "raw": { ... },         # LLM 生JSON
      "source": "openai_llm" or "fallback",
      "risk_delta": float,    # FUJI リスクに加算する値（-0.3〜+0.5 目安）
      "debate_summary": {...} # デバッグ / 監視用サマリ
    }
    """
    ctx = dict(context or {})

    # WorldModel スナップショット（失敗しても大丈夫なように try/except）
    try:
        world_snap = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = {}

    if not options:
        return _fallback_debate(options)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, options, ctx, world_snap)

    raw_text: str = ""
    parsed: Dict[str, Any] = {}

    try:
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

        # ---- 入力 options を id -> option に展開（ベース）----
        enriched_by_id: Dict[str, Dict[str, Any]] = {}
        for base in options:
            bid = base.get("id") or base.get("title") or "opt"
            base_copy = dict(base)
            base_copy.setdefault("id", bid)
            enriched_by_id[bid] = base_copy

        # ---- LLM 側の評価結果をマージ ----
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

        # ---- verdict が "却下" のものは基本的に最終候補から除外 ----
        non_rejected = [o for o in enriched_list if not _is_rejected(o)]

        # ---- chosen 判定 ----
        chosen: Optional[Dict[str, Any]] = None

        # 1) LLM が chosen_id を出していて、かつ却下でなければそれを採用
        if chosen_id and chosen_id in enriched_by_id:
            cand = enriched_by_id[chosen_id]
            if not _is_rejected(cand):
                chosen = cand

        # 2) それ以外の場合は「却下以外」の中から score 最大を選ぶ
        if chosen is None:
            candidates = non_rejected if non_rejected else enriched_list
            if candidates:
                best = None
                best_score = -1.0
                for opt in candidates:
                    try:
                        s = float(opt.get("score", 0.0) or 0.0)
                    except Exception:
                        s = 0.0
                    if s > best_score:
                        best_score = s
                        best = opt
                chosen = best

        # 3) それでも chosen が決まらなければフォールバック
        if chosen is None:
            return _fallback_debate(options)

        # ---- risk_delta / debate_summary を付与 ----
        risk_delta = _calc_risk_delta(chosen, enriched_list)
        summary = _build_debate_summary(chosen, enriched_list)

        return {
            "chosen": chosen,
            "options": enriched_list,
            "raw": parsed,
            "source": "openai_llm",
            "risk_delta": risk_delta,
            "debate_summary": summary,
        }

    except Exception:
        # LLM まわりで何かあったら安全側フォールバック
        return _fallback_debate(options)
