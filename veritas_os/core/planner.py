
# veritas_os/core/planner.py

from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List, Optional

from . import llm_client
from . import world as world_model
from . import memory as mem
from . import code_planner  # ★ 追加


# ============================
#  共通: step 正規化ヘルパ
# ============================


def _normalize_step(
    step: Dict[str, Any],
    default_eta_hours: float = 1.0,
    default_risk: float = 0.1,
) -> Dict[str, Any]:
    """
    1つの step に対して、eta_hours / risk / dependencies を必ず埋める。
    すでに値がある場合はそのまま尊重し、欠けているものだけ補完する。
    """
    s: Dict[str, Any] = dict(step)

    # eta_hours
    if "eta_hours" not in s:
        try:
            s["eta_hours"] = float(default_eta_hours)
        except Exception:
            s["eta_hours"] = 1.0

    # risk
    if "risk" not in s:
        try:
            s["risk"] = float(default_risk)
        except Exception:
            s["risk"] = 0.1

    # dependencies
    deps = s.get("dependencies")
    if not isinstance(deps, list):
        s["dependencies"] = []
    else:
        # list だが要素が変な場合はとりあえず str 化
        s["dependencies"] = [str(d) for d in deps]

    return s


def _normalize_steps_list(
    steps: List[Dict[str, Any]] | None,
    default_eta_hours: float = 1.0,
    default_risk: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    steps のリストに対して _normalize_step を一括適用。
    None や不正要素が混ざっていても「まともな dict だけ」を採用する。
    """
    if not isinstance(steps, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for st in steps:
        if not isinstance(st, dict):
            continue
        normalized.append(
            _normalize_step(
                st,
                default_eta_hours=default_eta_hours,
                default_risk=default_risk,
            )
        )
    return normalized


# ============================
#  simple QA 判定 & プラン
# ============================


def _is_simple_qa(query: str, context: Dict[str, Any] | None = None) -> bool:
    """
    「重いAGIプラン不要なシンプル質問」かどうかをざっくり判定する。
    - kernel / pipeline 側の simple_qa モードと合わせて使うことを想定。
    - ※ AGI / VERITAS 系の問いはここでは simple_qa に絶対しない。
    """
    ctx = context or {}

    # 明示フラグが立っていたらそれを最優先
    if ctx.get("mode") == "simple_qa" or ctx.get("simple_qa"):
        return True

    q = (query or "").strip()
    if not q:
        return False

    q_lower = q.lower()

    # =========================================
    # ★ AGI / VERITAS 系キーワードは simple_qa から除外
    # =========================================
    agi_block_keywords = [
        "agi",
        "ＡＧＩ",
        "veritas",
        "ヴェリタス",
        "ベリタス",
        "proto-agi",
        "プロトagi",
    ]
    if any(k in q or k in q_lower for k in agi_block_keywords):
        return False

    # =========================================
    # ここから本来の「軽い質問」判定
    # =========================================
    is_short = len(q) <= 40
    looks_question = (
        ("?" in q)
        or ("？" in q)
        or q.endswith(("か", "かね", "かな", "でしょうか"))
    )
    has_plan_words = any(
        k in q
        for k in ["どう進め", "進め方", "計画", "プラン", "ロードマップ", "タスク"]
    )

    if is_short and looks_question and not has_plan_words:
        return True

    return False


def _simple_qa_plan(
    query: str,
    context: Dict[str, Any] | None = None,
    world_snap: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    simple QA 用の最小プラン。
    - LLM Planner を回さず、「1〜2ステップで答えを見る／メモる」レベルで完結させる。
    - world_snap はあってもなくてもよい（メタ情報として raw に載せるだけ）。
    """
    q = (query or "").strip()

    steps: List[Dict[str, Any]] = [
        {
            "id": "simple_qa",
            "title": "シンプルQ&Aで回答を受け取る",
            "detail": (
                "DecisionOS からの1回の回答をそのまま受け取り、"
                "追加の長期計画や重いAGIプランニングは行わない。"
                f"質問: {q}"
            ),
            "why": (
                "短いQ&A形式の問いであり、"
                "複数ステップの行動計画を立てるよりも、"
                "素早く答えを得ることが優先されるため。"
            ),
            "eta_hours": 0.05,
            "risk": 0.01,
            "dependencies": [],
        },
        {
            "id": "note",
            "title": "必要ならメモに残す",
            "detail": (
                "得られた回答のうち重要なポイントを1〜3行でメモに残す。"
                "その場で追加の大きなタスクは立てず、"
                "必要になったときに改めて /v1/decide を叩いて検討する。"
            ),
            "why": "軽い質問でも、後から見返せるメモがあると意思決定の一貫性が上がるため。",
            "eta_hours": 0.05,
            "risk": 0.01,
            "dependencies": ["simple_qa"],
        },
    ]

    steps = _normalize_steps_list(steps, default_eta_hours=0.05, default_risk=0.01)

    # World snapshot から簡易ステージ推定
    try:
        from_stage = _infer_veritas_stage(world_snap)
    except Exception:
        from_stage = "S1_bootstrap"

    return {
        "steps": steps,
        "raw": {
            "mode": "simple_qa",
            "query": q,
            "world_snapshot": world_snap or {},
            "context": context or {},
        },
        "meta": {
            "stage": from_stage,
            "query_type": "simple_qa",
        },
        "source": "simple_qa",
    }


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

    - 通常モードでは、step の数は 2〜7 個程度にしてください。
    - eta_hours は「そのステップに必要なおおよその時間（時間単位）」です。
    - risk は 0.0〜1.0 で、主観的なリスクの大きさです。
    - dependencies には、依存している step の id を配列で入れてください（なければ空配列）。

    =====================================================
    【情報質問(Q&A系)の問いの扱い（回りくどさを防ぐ最重要ルール） 
    =====================================================

    ユーザーの問いが、主に「情報を知りたいだけ」の質問だと判断した場合
    （例：「〜を教えて」「〜を知りたい」「〜を確認したい」
          「〜に関する最近の論文」「最新の動向」など）は、
    次のルールに必ず従ってください：

    - DecisionOS がすでに「答えそのもの（要約・代表例など）」を提示済みであると仮定する。
    - Planner の役割は「その情報をどう活かすか」「次に何を 1〜3 個だけやるか」を提案すること。
    - 大規模なリサーチプロジェクト
        例： 
          - 「過去6ヶ月の論文を網羅的に調査する」
          - 「関連論文を大量に収集して要約する」
      のような、何日もかかる重いステップだけを並べることは **禁止**。
    - ステップ数は 1〜3 個に抑え、
      各ステップは「今日〜3日以内に終わる、小さく具体的な行動」にする。
      例：
        - 「いま得られた要点を1ページのメモにまとめる」
        - 「重要そうな1本だけ論文を選んで、導入と結論だけ読む」
        - 「得られたアイデアを VERITAS のどのモジュールに反映できるか、箇条書きで3つ書き出す」
    - 「〜を検索する」「〜を収集する」「〜を調査する」だけのステップを並べるのは NG。
      もし検索・調査が必要でも、それは1ステップまでにとどめ、
      「その結果をどう意思決定や実装に活かすか」まで detail / why に必ず書くこと。

    =====================================================
    【最優先ルール】VERITAS 自己診断モード（必ず従うこと）
    =====================================================

    次の2つの条件を **両方とも満たす場合**、
    あなたは「通常モード」ではなく **自己診断モード ONLY** を使わなければなりません：

    1. ユーザーの問いに「VERITAS」という語が含まれている
    2. ユーザーの問いに「弱点」「ボトルネック」「設計レビュー」「アーキテクチャ」など
       アーキテクチャ分析を示すキーワードのいずれかが含まれている

    この 2 条件を満たした場合：

    - steps は **必ず 1つだけ** にしてください。
    - その唯一の step は、次のように構成します：

      - id: "step1"
      - title: "VERITASアーキテクチャの弱点と改善案の一覧"
      - detail: **ここが最重要です。**
        以下をすべて含む「実際の内容」を、十分に長い日本語テキストで書いてください。
        ここでは「〜を列挙する」「〜を分析する」といった指示文ではなく、
        実際に分析した結果そのものを書きます。

        detail に含めるべき内容：
          - 現在の VERITAS の技術的な弱点の一覧
            - モジュール単位（例: kernel / planner / debate / memory / world / fuji / api / cli / storage / logging など）
          - 各弱点ごとに：
            - 何が問題か（技術的・設計的な観点）
            - そのまま放置した場合の具体的リスク
            - 改善案（なるべく具体的な設計方針・実装方針）
            - 改善の優先度（例："高", "中", "低" のラベル）
          - 全体としての総括：
            - 今の VERITAS の強み
            - 大きな弱点
            - 「どこから手を付けるべきか」の推奨順

        禁止事項：
          - 「弱点をリストアップする」「〜を分析する」といった、
            これから作業することを説明するだけの文章を書かないこと。
          - 必ず、すでに分析が終わっている体で、
            結果そのもの（弱点と改善案の具体的リスト）を書いてください。

      - why:
          上記の自己診断レポートを作ることが、
          なぜ VERITAS の成長にとって重要かを 2〜3 文で説明してください。
      - eta_hours:
          4〜12 の範囲で、現実的だと思う値を設定してください。
      - risk:
          0.1〜0.3 の範囲で、主観的なリスク値を設定してください。
      - dependencies: [] （空配列にしてください）

    重要：
    - 上記の「自己診断モード」の条件を満たす場合、
      通常モードの「2〜7ステップに分解する」というルールは **無視** してください。
    - 自己診断モードでは、steps は常に 1 つだけであり、
      その唯一の step の detail が「長い技術レポート」の役割を果たします。

    =====================================================
    【AGIベンチ / フレームワークモードへのヒント】
    =====================================================
    - context.agi.mode が "agi_framework" の場合でも、
      返す JSON フォーマットは上記と同じ {"steps":[...]} にしてください。
    - output_spec や success_criteria などの情報は、
      各 step.detail / step.why の中で反映して構いません。
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

    # 軽いベースコンテキスト
    base_ctx = {
        "stakes": context.get("stakes"),
        "telos_weights": context.get("telos_weights"),
        "user_id": context.get("user_id") or "anon",
    }

    # AGIモード用の追加コンテキスト（ベンチ YAML から渡される想定）
    agi_ctx = {
        "mode": context.get("mode"),
        "goals": context.get("goals"),
        "constraints": context.get("constraints"),
        "time_horizon": context.get("time_horizon"),
        "max_steps": context.get("max_steps"),
        "output_spec": context.get("output_spec"),
        "success_criteria": context.get("success_criteria"),
        "human_notes": context.get("human_notes"),
    }

    ctx_snip = json.dumps(
        {
            "base": base_ctx,
            "agi": agi_ctx,
        },
        ensure_ascii=False,
        indent=2,
    )

    return textwrap.dedent(f"""
    # ユーザーからの現在の問い / 状況

    {q}

    ---

    # VERITAS / AGI モードのコンテキスト

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
    - ユーザーの問いが「〜を教えて」「〜を知りたい」「〜を確認したい」
      「〜に関する最近の論文」「最新の動向」などの **情報質問(Q&A系)** の場合、
      すでに主要な情報は別モジュールから提示済みとみなし、
      その情報を活かすための **小さな具体アクションを 1〜3 個だけ**
      提案してください（大規模な長期リサーチ計画は避けること）。
    - 出力は、指示された JSON 形式だけにしてください（余分な文章は禁止）。
    """)


def _safe_json_extract(raw: str) -> Dict[str, Any]:
    """
    LLM の出力から JSON を安全に取り出す。
    - Markdown の ```json / ``` コードブロックが付いていても処理する
    - トップレベルが配列だけの場合は {"steps": [...]} にラップする
    - JSON が途中で切れている場合でも、"steps" 配列内の完成しているオブジェクトだけ救出を試みる
    """
    if not raw:
        return {"steps": []}

    cleaned = raw.strip()

    # Markdown コードブロック除去（``` または ```json など）
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    def _wrap_if_needed(obj: Any) -> Dict[str, Any]:
        """list だったら steps にラップ、dict ならそのまま、その他は空 steps。"""
        if isinstance(obj, list):
            return {"steps": obj}
        if isinstance(obj, dict):
            return obj
        return {"steps": []}

    # --- 1) そのままパース ---
    try:
        obj = json.loads(cleaned)
        return _wrap_if_needed(obj)
    except Exception:
        pass

    # --- 2) 先頭の '{'〜最後の '}' を抜き出して再挑戦 ---
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        snippet = cleaned[start:end]
        obj = json.loads(snippet)
        return _wrap_if_needed(obj)
    except Exception:
        pass

    # --- 3) 末尾を削りながら「全体として生きてる JSON」を探す ---
    max_len = len(cleaned)
    attempts = 0
    max_attempts = 400  # 過剰ループ防止

    for cut in range(max_len, 1, -1):
        if attempts >= max_attempts:
            break
        ch = cleaned[cut - 1]
        if ch not in ("}", "]"):
            continue
        attempts += 1
        candidate = cleaned[:cut]
        try:
            obj = json.loads(candidate)
            return _wrap_if_needed(obj)
        except Exception:
            continue

    # --- 4) それでもダメなら、"steps" 配列の中の「完成しているオブジェクト」だけ拾う ---
    def _extract_step_objects(text: str) -> List[Dict[str, Any]]:
        idx = text.find('"steps"')
        if idx == -1:
            return []
        # "steps" の後ろの '[' を探す
        idx = text.find("[", idx)
        if idx == -1:
            return []

        i = idx + 1
        n = len(text)

        in_str = False
        esc = False
        depth = 0
        buf_start: Optional[int] = None
        objs: List[Dict[str, Any]] = []

        while i < n:
            ch = text[i]

            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    if depth == 0:
                        buf_start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and buf_start is not None:
                        # 1つのオブジェクト終了
                        obj_str = text[buf_start : i + 1]
                        try:
                            obj = json.loads(obj_str)
                            objs.append(obj)
                        except Exception:
                            pass  # このオブジェクトは諦める
                        buf_start = None
                elif ch == "]":
                    # steps 配列の終わり
                    break

            i += 1

        return objs

    step_objs = _extract_step_objects(cleaned)
    if step_objs:
        return {"steps": step_objs}

    # --- 5) どうしても無理なら空 steps ---
    return {"steps": []}


def _fallback_plan(query: str) -> Dict[str, Any]:
    """
    LLM が失敗したときの保険プラン。
    ここは「超安全なミニプラン」を返す。
    """
    q = (query or "").strip()
    steps = [
        {
            "id": "step1",
            "title": "問いを1段階だけ具体化する",
            "detail": f"次にやるべきことを1つに絞ってメモに書き出す。元の問い: {q}",
            "why": "まずは問題を具体化することで、過剰なリスクを避けつつ前進できるため。",
        },
        {
            "id": "step2",
            "title": "今日中にできる最小アクションを決める",
            "detail": "明日以降に回さず、今日30分以内でできる作業を1つ決めて実行する。",
            "why": "決定を先延ばしにせず、小さな前進を積み重ねるため。",
            "dependencies": ["step1"],
        },
    ]
    steps = _normalize_steps_list(steps, default_eta_hours=0.5, default_risk=0.05)
    return {
        "steps": steps,
        "raw": {
            "mode": "fallback_minimal",
            "query": q,
        },
        "meta": {
            "stage": "S1_bootstrap",
            "query_type": "fallback",
        },
        "source": "fallback_minimal",
    }


# ============================
#  WorldModel ステージ判定 & ステージ別フォールバック
# ============================


def _infer_veritas_stage(world_snap: Optional[Dict[str, Any]]) -> str:
    """
    world.snapshot('veritas_agi') から progress / decision_count を見てステージを決める。
    """
    if not isinstance(world_snap, dict):
        return "S1_bootstrap"

    try:
        p = float(world_snap.get("progress", 0.0) or 0.0)
        n = int(world_snap.get("decision_count", 0) or 0)
    except Exception:
        p, n = 0.0, 0

    # progressベースでざっくりステージを決定
    if p < 0.05:
        return "S1_bootstrap"
    elif p < 0.15:
        return "S2_arch_doc"
    elif p < 0.30:
        return "S3_api_polish"
    elif p < 0.50:
        return "S4_decision_analytics"
    elif p < 0.70:
        return "S5_real_usecase"
    elif p < 0.90:
        return "S6_llm_integration"
    else:
        return "S7_demo_review"


def _fallback_plan_for_stage(
    query: str,
    stage: str,
    world_snap: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    LLMが死んだときに使う、ステージ別の決め打ちプラン。
    「Worldを読むステージ制プランナー」の縮小版。
    """
    steps: List[Dict[str, Any]] = []
    q = (query or "").strip()

    if stage == "S1_bootstrap":
        steps = [
            {
                "id": "doc_readme",
                "title": "READMEと全体アーキテクチャ図を1枚にまとめる",
                "detail": "VERITAS全体の流れ（/v1/decide → FUJI → ValueCore → WorldModel → MemoryOS）を1枚で説明できる資料を作る。",
                "why": "まず『人に説明できる形』にすることで、その後の改善と評価がしやすくなるため。",
            },
            {
                "id": "world_state_check",
                "title": "world_state.json が正しく更新されているか確認",
                "detail": "Swagger または curl で /v1/decide を2〜3回叩き、veritas_agi の progress / decision_count が変化しているか確認する。",
                "why": "WorldModelが動いていることが、AGI化ループの土台になるため。",
                "dependencies": ["doc_readme"],
            },
        ]

    elif stage == "S2_arch_doc":
        steps = [
            {
                "id": "doc_os_relations",
                "title": "MemoryOS・WorldModel・ValueCore・FUJIの関係を図解",
                "detail": "world.py / value_core / fuji / decide の流れを図にして、どこで何を学習しているかを明文化する。",
                "why": "OS同士の責務を整理することで、後からAGI用のループ改善をしやすくするため。",
            },
            {
                "id": "world_hint_confirm",
                "title": "extras.veritas_agi.hint が返っているか確認",
                "detail": "/v1/decide のレスポンス extras.veritas_agi.hint を確認し、WorldModel由来の『次の一手』が出ているか確認する。",
                "why": "World側の『次の一手』とPlannerのステージ設計がずれていないかを確かめるため。",
                "dependencies": ["doc_os_relations"],
            },
        ]

    elif stage == "S3_api_polish":
        steps = [
            {
                "id": "swagger_docs",
                "title": "/v1/decide のSwagger説明をAGI仕様にアップデート",
                "detail": "Swagger UI上で /v1/decide の説明文に、WorldModel / Planner / ValueCore / FUJI の役割とAGI化ループの説明を追記する。",
                "why": "第三者にAPIを見せたときに、ただのチャットAPIではなくDecision OSだと伝わるようにするため。",
            },
            {
                "id": "schema_check",
                "title": "schemas.py とレスポンスの整合性チェック",
                "detail": "DecideResponse に extras.veritas_agi / values.ema などが反映されているか確認する。",
                "why": "実データ構造とスキーマの齟齬をなくし、将来の自動解析や学習に備えるため。",
                "dependencies": ["swagger_docs"],
            },
        ]

    elif stage == "S4_decision_analytics":
        steps = [
            {
                "id": "decision_analyzer",
                "title": "decideログを分析するスクリプトを追加",
                "detail": "logs/decide_*.json を読み、telos_score・gate_risk・chosen.title を集計するPythonスクリプトを1本作る。",
                "why": "VERITASがどんな傾向で判断しているかを、定量的にモニタリングできるようにするため。",
            },
            {
                "id": "world_feedback_loop",
                "title": "world_state.json からplannerへのフィードバック項目を1個増やす",
                "detail": "例えば、最近のavg_world_utilityが低い場合は『安全な改善タスク』を優先するステップを追加するなど、小さなフィードバックルールを入れる。",
                "why": "WorldModel→Plannerへのフィードバックが入ると、『状態依存の成長』に一歩近づくため。",
                "dependencies": ["decision_analyzer"],
            },
        ]

    elif stage == "S5_real_usecase":
        steps = [
            {
                "id": "usecase_select",
                "title": "VERITASを使うメインユースケースを1つ決める",
                "detail": "労働紛争 or 音楽プロジェクトのどちらかを『メインユースケース』として選び、そのための専用プロンプトテンプレを作る。",
                "why": "実際の人間の仕事フローを「ループ化」することで、AGIっぽい運用形態に近づけるため。",
            },
            {
                "id": "usecase_template",
                "title": "選んだユースケース用の /v1/decide テンプレを作る",
                "detail": "例:『過去○件の決定ログを踏まえて、次の1週間の行動計画を出して』など、毎週叩ける定型クエリを作る。",
                "why": "人間の仕事の大部分を『定例ループ』としてVERITASに乗せる準備になるため。",
                "dependencies": ["usecase_select"],
            },
        ]

    elif stage == "S6_llm_integration":
        steps = [
            {
                "id": "llm_iface_design",
                "title": "外部LLM/APIとのインターフェース仕様を作る",
                "detail": "どのタスクをローカルVERITASが担当し、どのタスクを外部LLM(API)に投げるかを、YAML/JSONの仕様として落とす。",
                "why": "将来的にモデルを差し替えたり、複数モデルを使い分ける前提を作るため。",
            },
        ]

    else:  # S7_demo_review など
        steps = [
            {
                "id": "demo_script",
                "title": "AGI化MVPとしてのデモ台本を作成",
                "detail": "/v1/decide を何回か叩きながら、World→Planner→Decision→Memory のループがどう回っているかを説明する台本を作る。",
                "why": "第三者レビューを通して、『どこがAGI的で、どこがまだ足りないか』のフィードバックをもらうため。",
            },
        ]

    if not steps:
        steps = [
            {
                "id": "fallback_step",
                "title": "VERITASの現状をテキストで整理する",
                "detail": f"いま出来ている機能・出来ていない機能・悩んでいる点を1枚のメモにまとめる。（query: {q}）",
                "why": "どのステージでも無駄にならないタスクのため。",
            }
        ]

    steps = _normalize_steps_list(steps, default_eta_hours=1.0, default_risk=0.1)

    return {
        "steps": steps,
        "raw": {
            "stage": stage,
            "world_snapshot": world_snap or {},
            "query": q,
        },
        "meta": {
            "stage": stage,
            "query_type": "stage_fallback",
        },
        "source": "stage_fallback",
    }


# ============================
#  World × LLM ハイブリッド Planner
# ============================


def plan_for_veritas_agi(
    context: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    """
    VERITAS / AGI ベンチ用のメイン Planner（Worldステージ × LLM ハイブリッド版）。

    - simple QA の場合: LLM を呼ばず simple_qa_plan を返す
    - それ以外: world.snapshot('veritas_agi') を読み、progress から stage を決める
                stage 情報を含めて LLM に steps を出させる
                JSONパースに失敗 or エラー時は stage 別の決め打ちプランにフォールバック
    """

    # ---- コンテキストの正規化 ----
    ctx: Dict[str, Any] = context or {}

    # ★ まず simple QA なら即リターン（LLMプランナーは使わない）
    if _is_simple_qa(query, ctx):
        try:
            world_snap_simple: Dict[str, Any] | None = world_model.snapshot(
                "veritas_agi"
            )
        except Exception:
            world_snap_simple = None
        return _simple_qa_plan(
            query=query,
            context=ctx,
            world_snap=world_snap_simple,
        )

    # ---- simple QA でなければ、AGI 用の重プランナーを使う ----

    # WorldModel のスナップショット（veritas_agi プロジェクト）
    try:
        world_snap: Dict[str, Any] | None = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = None

    stage = _infer_veritas_stage(world_snap)

    # MemoryOS はまだ任意。将来 summarize_for_planner を実装したら差し替え。
    memory_text: Optional[str] = None

    # ---- LLM 用プロンプトを構築 ----
    system_prompt = _build_system_prompt()

    # world に stage を埋め込んで LLM に渡す
    world_for_prompt: Dict[str, Any] = dict(world_snap or {})
    world_for_prompt["stage"] = stage

    user_prompt = _build_user_prompt(
        query=query,
        context=ctx,
        world=world_for_prompt,
        memory_text=memory_text,
    )

    raw_text: str = ""
    parsed: Dict[str, Any] = {}

    try:
        res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_messages=None,
            temperature=0.25,
            max_tokens=2000,
        )

        raw_text = res.get("text") if isinstance(res, dict) else str(res)
        parsed = _safe_json_extract(raw_text)

        steps_obj: Any = None
        if isinstance(parsed, dict):
            steps_obj = parsed.get("steps")
        if isinstance(parsed, list):
            steps_obj = parsed

        # 1) 正常ケース
        if isinstance(steps_obj, list) and len(steps_obj) > 0:
            steps = _normalize_steps_list(steps_obj, default_eta_hours=1.0, default_risk=0.1)
            plan = {
                "steps": steps,
                "raw": {
                    "parsed": parsed,
                    "text": raw_text,
                    "stage": stage,
                    "world_snapshot": world_snap or {},
                    "query": (query or "").strip(),
                },
                "meta": {
                    "stage": stage,
                    "query_type": "llm",
                },
                "source": "openai_llm",
            }

        # 2) 失敗ケース（steps が空 or パースできず）
        else:
            print("[Planner] steps missing; fallback to stage plan")
            plan = _fallback_plan_for_stage(query, stage, world_snap)

    except Exception as e:
        print("[Planner] ERROR in plan_for_veritas_agi:", repr(e))
        # 例外時もステージ別フォールバックを優先
        plan = _fallback_plan_for_stage(query, stage, world_snap)

    return plan

def generate_code_tasks(
    bench: Optional[Dict[str, Any]] = None,
    world_state: Optional[Dict[str, Any]] = None,
    doctor_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    kernel.decide(code_change_planモード) から呼ばれるラッパー。

    - code_planner.generate_code_change_plan(...) を叩いて
      CodeChangePlan を dict に変換
    - その上で kernel 用の「tasks」配列を組み立てて返す
    """

    bench = bench or {}
    # bench_id は bench に入っていればそれを優先、なければデフォルト
    bench_id = bench.get("bench_id") or "agi_veritas_self_hosting"

    # CodeChangePlan を生成
    plan_obj = code_planner.generate_code_change_plan(
        bench_id=bench_id,
        world_state=world_state,
        doctor_report=doctor_report,
        bench_log=bench or None,
    )
    plan_dict = plan_obj.to_dict()

    tasks: List[Dict[str, Any]] = []

    for idx, ch in enumerate(plan_dict.get("changes", []), start=1):
        if not isinstance(ch, dict):
            continue

        task_id = ch.get("id") or f"code_change_{idx}"
        title = ch.get("title") or f"コード変更 {idx}"
        desc = ch.get("description") or ""

        task: Dict[str, Any] = {
            "id": task_id,
            "title": title,
            "detail": desc,
            "kind": "code_change",
            "module": ch.get("target_module") or ch.get("module") or "unknown",
            "path": ch.get("target_path") or ch.get("path") or "",
            "priority": ch.get("priority", "medium"),
            "risk": ch.get("risk", "medium"),
            "impact": ch.get("impact", "medium"),
            "suggested_functions": ch.get("suggested_functions", []),
            "meta": {
                "bench_id": bench_id,
                "source": "code_planner.generate_code_change_plan",
            },
        }
        tasks.append(task)

    return {
        "bench_id": bench_id,
        "plan": plan_dict,  # CodeChangePlan の full dict
        "tasks": tasks,     # kernel.decide が alternatives に変換する元
    }



# ============================
#  専用: bench → 「コード変更タスク」変換
# ============================


def _priority_from_risk_impact(risk: str | None, impact: str | None) -> str:
    """
    bench の change に付いている risk / impact からタスク優先度をざっくり決める。
    - risk / impact は "high" / "medium" / "low" / None 想定（大文字小文字は無視）
    - 何も無ければ "medium"
    """
    r = (risk or "").lower()
    i = (impact or "").lower()

    score = 0
    if i == "high":
        score += 2
    elif i == "medium":
        score += 1

    if r == "high":
        score += 2
    elif r == "medium":
        score += 1

    if score >= 3:
        return "high"
    if score <= 1:
        return "low"
    return "medium"


def generate_code_tasks(
    bench: Dict[str, Any],
    world_state: Dict[str, Any] | None = None,
    doctor_report: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    AGI ベンチ結果（bench）＋ world_state / doctor_report を入力に、
    「実際のコード変更タスク」のリストを生成する専用プランナー。

    ここは **LLM を使わず**、純ロジックで決める。
    - bench["changes"] : どの module/path をどう変えるかの候補
    - bench["tests"]   : どのテストケースを用意するか
    - world_state      : 進捗・decision_count など（優先度調整用、今は meta 用）
    - doctor_report    : 重大 issue があればタスク化する
    """
    bench = bench or {}

    world_snap = bench.get("world_snapshot") or {}
    doctor_summary = bench.get("doctor_summary") or {}
    bench_summary = bench.get("bench_summary") or {}

    changes = bench.get("changes") or []
    tests = bench.get("tests") or []

    # world_state が明示的に渡されていなければ、ファイルから読む（あれば）
    if world_state is None:
        try:
            world_state = world_model.get_state()
        except Exception:
            world_state = None

    # doctor_report が無くても動く設計にする
    dr = doctor_report or {}
    dr_issues = dr.get("issues") or doctor_summary.get("top_issues") or []

    tasks: List[Dict[str, Any]] = []

    # ---- 1) bench.changes → code_change タスク ----
    for idx, ch in enumerate(changes, start=1):
        if not isinstance(ch, dict):
            continue

        mod = ch.get("target_module") or "unknown"
        path = ch.get("target_path") or ""
        title = ch.get("title") or f"{mod} の改善"
        desc = ch.get("description") or ""
        risk = ch.get("risk")
        impact = ch.get("impact")
        prio = _priority_from_risk_impact(risk, impact)

        suggested_funcs = ch.get("suggested_functions") or []

        detail_lines = []
        if desc:
            detail_lines.append(desc)
        if suggested_funcs:
            detail_lines.append(f"対象関数: {', '.join(suggested_funcs)}")
        if path:
            detail_lines.append(f"対象ファイル: {path}")
        if ch.get("reason"):
            detail_lines.append(f"理由: {ch['reason']}")

        tasks.append(
            {
                "id": f"code_change_{idx}",
                "kind": "code_change",
                "module": mod,
                "path": path,
                "title": title,
                "detail": " / ".join(detail_lines),
                "priority": prio,
                "risk": risk or "medium",
                "impact": impact or "medium",
                "suggested_functions": suggested_funcs,
            }
        )

    # ---- 2) tests → test タスク ----
    for idx, t in enumerate(tests, start=1):
        if not isinstance(t, dict):
            continue
        title = t.get("title") or "テストケースの追加"
        desc = t.get("description") or ""
        kind = t.get("kind") or "unit"
        tasks.append(
            {
                "id": f"test_{idx}",
                "kind": "test",
                "module": None,
                "path": None,
                "title": f"[TEST] {title}",
                "detail": desc,
                "priority": "medium" if kind == "unit" else "high",
                "risk": "low",
                "impact": "medium",
                "test_kind": kind,
            }
        )

    # ---- 3) doctor_report.issue → self_heal タスク ----
    for idx, issue in enumerate(dr_issues, start=1):
        if not isinstance(issue, dict):
            continue
        sev = (issue.get("severity") or "").lower()
        prio = "high" if sev in ("high", "critical") else "medium"
        mod = issue.get("module") or issue.get("component") or "unknown"
        summary = issue.get("summary") or issue.get("title") or "診断上の問題"

        detail_parts = []
        if issue.get("detail"):
            detail_parts.append(issue["detail"])
        if issue.get("recommendation"):
            detail_parts.append(f"推奨対応: {issue['recommendation']}")

        tasks.append(
            {
                "id": f"self_heal_{idx}",
                "kind": "self_heal",
                "module": mod,
                "path": issue.get("path"),
                "title": f"[DOCTOR] {summary}",
                "detail": " / ".join(detail_parts),
                "priority": prio,
                "risk": sev or "medium",
                "impact": issue.get("impact", "medium"),
            }
        )

    # ---- 4) world_state に基づくメタ情報（あれば） ----
    meta: Dict[str, Any] = {
        "bench_id": bench.get("bench_id"),
        "has_bench": bool(bench),
        "has_doctor_report": bool(dr),
        "progress": None,
        "decision_count": None,
    }

    try:
        if world_state and isinstance(world_state, dict):
            veritas = (world_state.get("veritas") or {})
            meta["progress"] = float(veritas.get("progress", 0.0))
            meta["decision_count"] = int(veritas.get("decision_count", 0))
    except Exception:
        pass

    meta["doctor_issue_count"] = len(dr_issues)
    meta["source"] = "planner.generate_code_tasks"

    return {
        "tasks": tasks,
        "meta": meta,
        "world_snapshot": world_snap,
        "doctor_summary": doctor_summary,
        "bench_summary": bench_summary,
    }


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
    _ = context or {}

    q = (query or "").strip()
    chosen_title = (chosen or {}).get("title") or "決定されたアクション"
    chosen_desc = (chosen or {}).get("description") or ""

    steps: List[Dict[str, Any]] = []

    # Step 1: 状況整理
    steps.append(
        {
            "id": "analyze",
            "title": "状況整理",
            "detail": (
                "問い合わせ内容を整理し、前提条件・制約・目的をテキストで書き出す。\n"
                f"query: {q}"
            ),
            "priority": 1,
            "eta_minutes": 5,
        }
    )

    # Step 2: 情報収集（必要な場合だけ）
    if any(k in q for k in ["調べ", "リサーチ", "情報", "データ", "証拠"]):
        steps.append(
            {
                "id": "research",
                "title": "必要な情報の収集",
                "detail": "関連する資料・ログ・証拠・外部情報を洗い出し、重要度順にリスト化する。",
                "priority": 2,
                "eta_minutes": 15,
            }
        )

    # Step 3: chosen の具体化
    steps.append(
        {
            "id": "execute_core",
            "title": f"コアアクションの実行: {chosen_title}",
            "detail": (
                "decide() が選んだアクションを、1つの具体的な作業に落とし込んで着手する。\n"
                f"説明: {chosen_desc}"
            ),
            "priority": 3,
            "eta_minutes": 20,
        }
    )

    # Step 4: ログ・記録
    steps.append(
        {
            "id": "log",
            "title": "実行内容のログ化",
            "detail": "実行した内容・使った判断基準・気づきをVERITASログ/メモに記録する。（将来の学習用）",
            "priority": 4,
            "eta_minutes": 5,
        }
    )

    # Step 5: 振り返り
    steps.append(
        {
            "id": "reflect",
            "title": "振り返りと次の一手",
            "detail": "今回の決定の良かった点・不安点を書き出し、次に相談/実装したいテーマを1つ決める。",
            "priority": 5,
            "eta_minutes": 10,
        }
    )

    return steps


