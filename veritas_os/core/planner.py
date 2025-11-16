# veritas/core/planner.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json, textwrap

from . import llm_client
from . import world as world_model
from . import memory as mem


# ============================
#  LLM PlannerOS (メイン)
# ============================

def _build_system_prompt() -> str:
    """
    PlannerOS 用の system プロンプト。
    VERITAS 全体の文脈で「安全で実行可能なステップ計画」を組む役割。
    """
    return textwrap.dedent("""
    あなたは「VERITAS OS」の Planner モジュールです。
    役割は、ユーザーの問いや状況から、
    - 最小ステップで前進できる
    - 安全で、リスクが低い
    - 実行可能で、具体的な

    行動プラン（ステップのリスト）を作ることです。

    必ず JSON だけを返してください。前後に説明文やコメントを書かないでください。
    JSON のトップレベルは次の形式にしてください：

    {
      "steps": [
        {
          "id": "step1",
          "title": "短い日本語タイトル",
          "detail": "やることを1〜3文で説明",
          "why": "このステップが有効な理由",
          "eta_hours": 0.5,
          "risk": 0.1,
          "dependencies": []
        }
      ]
    }

    - step の数は 2〜7 個程度にしてください。
    - eta_hours は「そのステップに必要なおおよその時間（時間単位）」です。
    - risk は 0.0〜1.0 で、主観的なリスクの大きさです。
    - dependencies には、依存している step の id を配列で入れてください（なければ空配列）。
    """)


def _build_user_prompt(
    query: str,
    context: Dict[str, Any],
    world: Dict[str, Any] | None,
    memory_text: Optional[str],
) -> str:
    """
    LLM に渡す user プロンプトを組み立てる。
    world_state / MemoryOS の情報はあくまで「参考」として埋め込む。
    """
    q = (query or "").strip()

    world_snip = json.dumps(world or {}, ensure_ascii=False, indent=2)
    mem_snip = memory_text or "(MemoryOS からの重要メモはありません)"

    ctx_snip = json.dumps(
        {
            "stakes": context.get("stakes"),
            "telos_weights": context.get("telos_weights"),
            "user_id": context.get("user_id") or "anon",
        },
        ensure_ascii=False,
        indent=2,
    )

    return textwrap.dedent(f"""
    # ユーザーからの現在の問い / 状況

    {q}

    ---

    # VERITAS の現在の文脈（抜粋）

    {ctx_snip}

    ---

    # WorldModel のスナップショット（要約用）

    {world_snip}

    ---

    # MemoryOS からの重要なメモ（要約）

    {mem_snip}

    ---

    上記を踏まえて、「今から 1〜3 日以内に実際に実行できる」範囲で、
    最小ステップで前進できる行動プランを作成してください。

    重要：
    - 抽象的なスローガンではなく、「具体的に何をするか」が分かるようにしてください。
    - リスクが高い行動は避け、安全で合法的な範囲で計画してください。
    - 出力は、指示された JSON 形式だけにしてください（余分な文章は禁止）。
    """)


def _safe_json_extract(raw: str) -> Dict[str, Any]:
    """
    LLM の出力から JSON を安全に取り出す。
    - そのまま json.loads が通ればそれを使う。
    - ダメなら `{` から最後の `}` までを探して再トライ。
    - それでもダメなら簡易プランを返す。
    """
    if not raw:
        return {"steps": []}

    # まずは素直にパース
    try:
        return json.loads(raw)
    except Exception:
        pass

    # 先頭の '{' 〜 最後の '}' を抜き出して再挑戦
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        snippet = raw[start:end]
        return json.loads(snippet)
    except Exception:
        # それでもダメならフォールバック
        return {"steps": []}


def _fallback_plan(query: str) -> Dict[str, Any]:
    """
    LLM が失敗したときの保険プラン。
    ここは「超安全なミニプラン」を返す。
    """
    q = (query or "").strip()
    return {
        "steps": [
            {
                "id": "step1",
                "title": "問いを1段階だけ具体化する",
                "detail": f"次にやるべきことを1つに絞ってメモに書き出す。元の問い: {q}",
                "why": "まずは問題を具体化することで、過剰なリスクを避けつつ前進できるため。",
                "eta_hours": 0.25,
                "risk": 0.05,
                "dependencies": [],
            },
            {
                "id": "step2",
                "title": "今日中にできる最小アクションを決める",
                "detail": "明日以降に回さず、今日30分以内でできる作業を1つ決めて実行する。",
                "why": "決定を先延ばしにせず、小さな前進を積み重ねるため。",
                "eta_hours": 0.5,
                "risk": 0.05,
                "dependencies": ["step1"],
            },
        ]
    }


def plan_for_veritas_agi(context: Dict[str, Any], query: str) -> Dict[str, Any]:
    """
    server.py から呼ばれるメイン入口。
    - query / context / world_state / MemoryOS をもとに
      LLM で行動プランを作成する。
    - 失敗時はローカルのフォールバックプランを返す。

    戻り値形式:
    {
      "steps": [...],
      "raw": "<LLM生テキスト or 空文字>",
      "source": "openai_llm" or "fallback"
    }
    """
    ctx = dict(context or {})
    # ---- WorldModel / MemoryOS から補助情報を取得 ----
    try:
        world_snap = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = {}

    # MemoryOS から最近の重要メモをテキストにする（実装がなければ None）
    mem_text: Optional[str] = None
    try:
        uid = ctx.get("user_id") or "anon"
        if hasattr(mem, "export_recent_for_prompt"):
            mem_text = mem.export_recent_for_prompt(uid, limit=5)
    except Exception:
        mem_text = None

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, ctx, world_snap, mem_text)

    raw_text: str = ""
    parsed: Dict[str, Any] = {}

    try:
        res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_messages=None,
            temperature=0.25,
            max_tokens=800,
        )

        raw_text = res.get("text") if isinstance(res, dict) else str(res)
        parsed = _safe_json_extract(raw_text)
        steps = parsed.get("steps") or []
        if not isinstance(steps, list) or not steps:
            raise ValueError("no steps parsed")

        plan: Dict[str, Any] = {
            "steps": steps,
            # ★ ここをテキストではなく dict にする
            "raw": parsed,
            "source": "openai_llm",
        }

    except Exception:
        plan = _fallback_plan(query)
        # 失敗時は raw を None にしておく
        plan["raw"] = None
        plan["source"] = "fallback"

    return plan


# ============================
#  後方互換: 旧 generate_plan
# ============================

def generate_plan(
    query: str,
    chosen: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """
    旧バージョンとの互換用。
    - もし他のコードが generate_plan() を使っていても壊れないように、
      シンプルなルールベース版を維持しておく。
    - /v1/decide のメイン経路は plan_for_veritas_agi() を使う。
    """
    ctx = context or {}

    q = (query or "").strip()
    chosen_title = (chosen or {}).get("title") or "決定されたアクション"
    chosen_desc = (chosen or {}).get("description") or ""

    steps: List[Dict[str, Any]] = []

    # Step 1: 状況整理
    steps.append({
        "id": "analyze",
        "title": "状況整理",
        "detail": (
            "問い合わせ内容を整理し、前提条件・制約・目的をテキストで書き出す。\n"
            f"query: {q}"
        ),
        "priority": 1,
        "eta_minutes": 5,
    })

    # Step 2: 情報収集（必要な場合だけ）
    if any(k in q for k in ["調べ", "リサーチ", "情報", "データ", "証拠"]):
        steps.append({
            "id": "research",
            "title": "必要な情報の収集",
            "detail": "関連する資料・ログ・証拠・外部情報を洗い出し、重要度順にリスト化する。",
            "priority": 2,
            "eta_minutes": 15,
        })

    # Step 3: chosen の具体化
    steps.append({
        "id": "execute_core",
        "title": f"コアアクションの実行: {chosen_title}",
        "detail": (
            "decide() が選んだアクションを、1つの具体的な作業に落とし込んで着手する。\n"
            f"説明: {chosen_desc}"
        ),
        "priority": 3,
        "eta_minutes": 20,
    })

    # Step 4: ログ・記録
    steps.append({
        "id": "log",
        "title": "実行内容のログ化",
        "detail": "実行した内容・使った判断基準・気づきをVERITASログ/メモに記録する。（将来の学習用）",
        "priority": 4,
        "eta_minutes": 5,
    })

    # Step 5: 振り返り
    steps.append({
        "id": "reflect",
        "title": "振り返りと次の一手",
        "detail": "今回の決定の良かった点・不安点を書き出し、次に相談/実装したいテーマを1つ決める。",
        "priority": 5,
        "eta_minutes": 10,
    })

    return steps
