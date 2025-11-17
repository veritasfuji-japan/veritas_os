# veritas_os/core/debate.py
"""
ReasonOS Multi-Agent Debate モジュール（MVP版）

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


def _safe_parse(raw: str) -> Dict[str, Any]:
    """
    LLM 出力から JSON を安全に取り出すユーティリティ。
    - まずはそのまま json.loads
    - 失敗したら { ... } の部分を抽出して再トライ
    - それでもダメなら最小構造で返す
    """
    if not raw:
        return {"options": [], "chosen_id": None}

    try:
        return json.loads(raw)
    except Exception:
        pass

    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        snippet = raw[start:end]
        return json.loads(snippet)
    except Exception:
        return {"options": [], "chosen_id": None}


def _fallback_debate(
    options: List[Dict[str, Any]]
) -> Dict[str, Any]:
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

    return {
        "options": enriched,
        "chosen": enriched[0],
        "raw": None,
        "source": "fallback",
    }


def run_debate(
    query: str,
    options: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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
      "source": "openai_llm" or "fallback"
    }
    """
    ctx = dict(context or {})

    # WorldModel スナップショット（あれば使う）
    try:
        world_snap = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = {}

    # 万が一 options が空ならフォールバック
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

        # id -> enriched option マップ
        enriched_by_id: Dict[str, Dict[str, Any]] = {}

        # 入力 options と LLM の評価をマージ
        for base in options:
            bid = base.get("id") or base.get("title") or "opt"
            base_copy = dict(base)
            enriched_by_id[bid] = base_copy

        for o in out_opts:
            if not isinstance(o, dict):
                continue
            oid = o.get("id")
            if not oid or oid not in enriched_by_id:
                continue
            target = enriched_by_id[oid]
            # LLM 側のフィールドを上書き（score, views, summary 等）
            for k, v in o.items():
                target[k] = v

        enriched_list = list(enriched_by_id.values())

        # chosen 判定
        chosen = None
        if chosen_id and chosen_id in enriched_by_id:
            chosen = enriched_by_id[chosen_id]
        else:
            # chosen_id がない場合は、score 最大のものを選ぶ
            best = None
            best_score = -1.0
            for opt in enriched_list:
                s = float(opt.get("score", 0.0) or 0.0)
                if s > best_score:
                    best_score = s
                    best = opt
            chosen = best or enriched_list[0]

        return {
            "chosen": chosen,
            "options": enriched_list,
            "raw": parsed,
            "source": "openai_llm",
        }

    except Exception:
        # 何かあればフォールバック
        return _fallback_debate(options)
