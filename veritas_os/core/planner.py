
# veritas_os/core/planner.py
from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import Any, Dict, List, Optional, TypedDict

from . import llm_client
from . import world as world_model
from . import memory as mem
from . import code_planner  # ★ 追加

logger = logging.getLogger(__name__)

# LLMの暴走出力によるJSON救出時の過剰CPU使用を抑えるための上限
_MAX_JSON_EXTRACT_CHARS = 200_000


def _truncate_json_extract_input(raw: str) -> str:
    """Limit JSON extraction input size to reduce parser and regex DoS risk."""
    cleaned = raw.strip()
    if len(cleaned) <= _MAX_JSON_EXTRACT_CHARS:
        return cleaned

    logger.warning(
        "planner JSON extraction input too large (%d chars); truncating to %d chars",
        len(cleaned),
        _MAX_JSON_EXTRACT_CHARS,
    )
    return cleaned[:_MAX_JSON_EXTRACT_CHARS]


class StepDict(TypedDict, total=False):
    """Planner step definition for normalized step payloads."""

    id: str
    title: str
    detail: str
    why: str
    eta_hours: float
    risk: float
    dependencies: List[str]


class PlanDict(TypedDict, total=False):
    """Planner plan payload containing normalized steps and metadata."""

    steps: List[StepDict]
    raw: Dict[str, Any]
    meta: Dict[str, Any]
    source: str

# ============================
#  step1（棚卸し）意図判定
# ============================

def _wants_inventory_step(query: str, context: Dict[str, Any] | None = None) -> bool:
    """
    「棚卸し/現状整理/step1で進めて」など、inventory(step1)系を明示的に求めているか。
    ここで True のときだけ step1 を“特別扱い”してよい前提にする。
    """
    _ = context or {}
    q = (query or "").strip()
    if not q:
        return False
    ql = q.lower()

    # 明示の step 指定
    if "step1" in ql or "step 1" in ql:
        return True

    # 棚卸し/現状整理
    if "棚卸" in q or "棚おろし" in q:
        return True
    if ("現状" in q) and ("整理" in q or "把握" in q or "棚卸" in q):
        return True

    # 英語寄り
    if "inventory" in ql:
        return True

    return False


# ============================
#  共通: step 正規化ヘルパ
# ============================

def _normalize_step(
    step: StepDict,
    default_eta_hours: float = 1.0,
    default_risk: float = 0.1,
) -> StepDict:
    """
    1つの step に対して、eta_hours / risk / dependencies を安全な値へ正規化する。

    - eta_hours: 数値へ変換し、負値は 0.0 に丸める
    - risk: 数値へ変換し、0.0〜1.0 の範囲へ丸める
    - dependencies: list[str] に正規化

    既存値がある場合も型不正な値は補正し、後続処理での型崩れを防ぐ。
    """
    s: StepDict = dict(step)

    try:
        fallback_eta = float(default_eta_hours)
    except Exception:
        fallback_eta = 1.0

    eta_candidate = s.get("eta_hours", fallback_eta)
    try:
        eta_hours = float(eta_candidate)
    except Exception:
        eta_hours = fallback_eta
    s["eta_hours"] = max(0.0, eta_hours)

    try:
        fallback_risk = float(default_risk)
    except Exception:
        fallback_risk = 0.1

    risk_candidate = s.get("risk", fallback_risk)
    try:
        risk_value = float(risk_candidate)
    except Exception:
        risk_value = fallback_risk
    s["risk"] = min(1.0, max(0.0, risk_value))

    deps = s.get("dependencies")
    if not isinstance(deps, list):
        s["dependencies"] = []
    else:
        s["dependencies"] = [str(d) for d in deps]

    return s


def _normalize_steps_list(
    steps: List[StepDict] | None,
    default_eta_hours: float = 1.0,
    default_risk: float = 0.1,
) -> List[StepDict]:
    """
    steps のリストに対して _normalize_step を一括適用。
    None や不正要素が混ざっていても「まともな dict だけ」を採用する。
    """
    if not isinstance(steps, list):
        return []

    normalized: List[StepDict] = []
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

    if ctx.get("mode") == "simple_qa" or ctx.get("simple_qa"):
        return True

    q = (query or "").strip()
    if not q:
        return False

    q_lower = q.lower()

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

    is_short = len(q) <= 40
    question_prefixes = (
        "what",
        "why",
        "when",
        "where",
        "who",
        "which",
        "how",
        "can ",
        "could ",
        "should ",
        "is ",
        "are ",
        "do ",
        "does ",
        "did ",
    )
    question_endings = (
        "か",
        "かね",
        "かな",
        "でしょうか",
        "教えて",
        "を教えて",
        "知りたい",
    )
    looks_question = (
        ("?" in q)
        or ("？" in q)
        or q_lower.startswith(question_prefixes)
        or q.endswith(question_endings)
    )
    has_plan_words = any(
        k in q for k in ["どう進め", "進め方", "計画", "プラン", "ロードマップ", "タスク"]
    )

    if is_short and looks_question and not has_plan_words:
        return True

    return False


def _simple_qa_plan(
    query: str,
    context: Dict[str, Any] | None = None,
    world_snap: Optional[Dict[str, Any]] = None,
) -> PlanDict:
    """
    simple QA 用の最小プラン。
    """
    q = (query or "").strip()

    steps: List[StepDict] = [
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
          "id": "s1",
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
    【情報質問(Q&A系)の扱い（回りくどさ防止）】
    =====================================================
    ユーザーの問いが「情報を知りたいだけ」の質問だと判断した場合
    （例：「〜を教えて」「〜を知りたい」「〜を確認したい」「最新の動向」など）は、
    - すでに主要情報は別モジュールから提示済みと仮定する
    - Planner は「その情報をどう活かすか」の小さな具体アクションを 1〜3 個だけ提案する
    - 何日もかかる網羅調査だけを並べるのは禁止

    =====================================================
    【step1(棚卸し)の誤爆防止ルール（重要）】
    =====================================================
    context.base.disallow_step1 が true の場合：
    - id が "step1" の step を **出力してはいけません**
    - 「棚卸し/現状整理の長文レポートを step1 に出す」形式も禁止です
    代わりに、通常の 2〜7 steps（または情報質問なら 1〜3 steps）で答えてください。

    =====================================================
    【AGIベンチ / フレームワークモードへのヒント】
    =====================================================
    - context.agi.mode が "agi_framework" の場合でも、
      返す JSON フォーマットは上記と同じ {"steps":[...]} にしてください。
    """)


def _build_user_prompt(
    query: str,
    context: Dict[str, Any],
    world: Dict[str, Any] | None,
    memory_text: Optional[str],
) -> str:
    """
    LLM に渡す user プロンプトを組み立てる。
    """
    q = (query or "").strip()
    world_snip = json.dumps(world or {}, ensure_ascii=False, indent=2)
    mem_snip = memory_text or "(MemoryOS からの重要メモはありません)"

    wants_step1 = _wants_inventory_step(q, context)
    disallow_step1 = not wants_step1

    base_ctx = {
        "stakes": context.get("stakes"),
        "telos_weights": context.get("telos_weights"),
        "user_id": context.get("user_id") or "anon",
        "wants_step1_inventory": bool(wants_step1),
        "disallow_step1": bool(disallow_step1),
    }

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

    ctx_snip = json.dumps({"base": base_ctx, "agi": agi_ctx}, ensure_ascii=False, indent=2)

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
    - 情報質問(Q&A系)なら、小さな具体アクションを 1〜3 個だけに抑えてください。
    - 出力は JSON 形式のみ（余分な文章は禁止）。
    """)


# ============================
#  JSON Parse（救出強化 + テスト互換）
# ============================

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

def _safe_parse(raw: Any) -> Dict[str, Any]:
    """
    テスト互換用（debate と同系）。
    - dict -> dict
    - list -> {"steps": list}
    - str  -> fenced除去 + JSON救出
    - その他 -> str化して救出
    戻りは必ず {"steps": [...]} を含む dict。
    """
    if raw is None:
        return {"steps": []}

    if isinstance(raw, dict):
        d = dict(raw)
        # steps が list でなければ空に寄せる
        if not isinstance(d.get("steps"), list):
            if isinstance(d.get("steps"), dict):
                d["steps"] = [d["steps"]]  # 変なモデル出力救済
            else:
                d.setdefault("steps", [])
        return d

    if isinstance(raw, list):
        return {"steps": raw}

    if not isinstance(raw, str):
        raw = str(raw)

    s = _truncate_json_extract_input(raw)
    if not s:
        return {"steps": []}

    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    return _safe_json_extract_core(s)


def _safe_json_extract_core(raw: str) -> Dict[str, Any]:
    """
    LLM の出力から JSON を安全に取り出す（救出エンジン）。
    ※ _safe_parse が外側の互換層。
    大きすぎる入力は先頭のみを使って解析し、DoSリスクを低減する。
    """
    if not raw:
        return {"steps": []}

    cleaned = _truncate_json_extract_input(raw)

    # ``` の先頭/末尾だけ来た時も対策
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    def _wrap_if_needed(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, list):
            return {"steps": obj}
        if isinstance(obj, dict):
            if isinstance(obj.get("steps"), list):
                return obj
            # stepsが無い/壊れてる場合も必ず安定化
            obj.setdefault("steps", [])
            if isinstance(obj.get("steps"), dict):
                obj["steps"] = [obj["steps"]]
            elif not isinstance(obj.get("steps"), list):
                obj["steps"] = []
            return obj
        return {"steps": []}

    def _decode_first_json_value(text: str) -> Any:
        """Extract and decode the first JSON value found in free-form text."""
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch not in "[{":
                continue
            try:
                obj, _ = decoder.raw_decode(text, idx=i)
                return obj
            except json.JSONDecodeError:
                continue
        return None

    # 1) そのまま
    try:
        obj = json.loads(cleaned)
        return _wrap_if_needed(obj)
    except Exception:
        logger.debug("planner JSON parse attempt 1 (raw) failed")

    # 1.5) 先頭ノイズ付きの JSON を raw_decode で救済
    obj = _decode_first_json_value(cleaned)
    if isinstance(obj, list):
        return _wrap_if_needed(obj)
    if isinstance(obj, dict) and "steps" in obj:
        return _wrap_if_needed(obj)

    # 2) {} 抜き出し（旧来互換の救済）
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        snippet = cleaned[start:end]
        obj = json.loads(snippet)
        return _wrap_if_needed(obj)
    except Exception:
        logger.debug("planner JSON parse attempt 2 (brace extraction) failed")

    # 3) 末尾削り
    max_len = len(cleaned)
    attempts = 0
    max_attempts = 500

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

    # 4) "steps":[{...},{...}] から dict だけ拾う（最後の保険）
    def _extract_step_objects(text: str) -> List[Dict[str, Any]]:
        idx = text.find('"steps"')
        if idx == -1:
            return []
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
                    if depth == 0:
                        # 先頭側の壊れた `}` を無視して復旧可能性を維持する
                        i += 1
                        continue
                    depth -= 1
                    if depth == 0 and buf_start is not None:
                        obj_str = text[buf_start : i + 1]
                        try:
                            obj = json.loads(obj_str)
                            if isinstance(obj, dict):
                                objs.append(obj)
                        except Exception:
                            logger.debug("planner step object parse failed: %s", obj_str[:80])
                        buf_start = None
                elif ch == "]":
                    break

            i += 1

        return objs

    step_objs = _extract_step_objects(cleaned)
    if step_objs:
        return {"steps": step_objs}

    return {"steps": []}


def _safe_json_extract(raw: str) -> Dict[str, Any]:
    """
    互換のため残す（既存コード/テストが参照する可能性）。
    実体は _safe_parse → _safe_json_extract_core。
    """
    return _safe_parse(raw)


# ============================
#  fallback（超安全）
# ============================

def _fallback_plan(query: str, *, disallow_step1: bool = False) -> Dict[str, Any]:
    """
    LLM が失敗したときの保険プラン（超安全なミニプラン）。
    ※ disallow_step1=True の時は id を step1 にしない（誤爆回避）。
    """
    q = (query or "").strip()

    if disallow_step1:
        steps = [
            {
                "id": "clarify",
                "title": "問いを1段階だけ具体化する",
                "detail": f"次にやるべきことを1つに絞ってメモに書き出す。元の問い: {q}",
                "why": "まずは問題を具体化することで、過剰なリスクを避けつつ前進できるため。",
            },
            {
                "id": "micro_action",
                "title": "今日中にできる最小アクションを決める",
                "detail": "明日以降に回さず、今日30分以内でできる作業を1つ決めて実行する。",
                "why": "決定を先延ばしにせず、小さな前進を積み重ねるため。",
                "dependencies": ["clarify"],
            },
        ]
    else:
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
        "raw": {"mode": "fallback_minimal", "query": q},
        "meta": {"stage": "S1_bootstrap", "query_type": "fallback"},
        "source": "fallback_minimal",
    }


# ============================
#  WorldModel ステージ判定 & ステージ別フォールバック
# ============================

def _infer_veritas_stage(world_state: Optional[Dict[str, Any]]) -> str:
    if not world_state:
        return "S1_bootstrap"

    try:
        progress = float(world_state.get("progress") or 0.0)
    except (TypeError, ValueError):
        progress = 0.0

    if progress < 0.05:
        return "S1_bootstrap"
    if progress < 0.15:
        return "S2_arch_doc"
    if progress < 0.35:
        return "S3_api_polish"
    if progress < 0.55:
        return "S4_decision_analytics"
    if progress < 0.70:
        return "S5_real_usecase"
    if progress < 0.90:
        return "S6_llm_integration"
    return "S7_demo_review"


def _fallback_plan_for_stage(
    query: str,
    stage: str,
    world_snap: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
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
    else:
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
        "raw": {"stage": stage, "world_snapshot": world_snap or {}, "query": q},
        "meta": {"stage": stage, "query_type": "stage_fallback"},
        "source": "stage_fallback",
    }


# ============================
#  World × LLM ハイブリッド Planner
# ============================

def _try_get_memory_snippet(query: str, ctx: Dict[str, Any]) -> Optional[str]:
    """
    MemoryOS が実装差分でも落ちない安全取得。
    - あれば 3〜5件くらいを短く連結
    - 無ければ None
    """
    q = (query or "").strip()
    if not q:
        return None

    try:
        # よくある名前を順に試す（実装差分吸収）
        if hasattr(mem, "search"):
            hits = mem.search(q, top_k=5)  # type: ignore[arg-type]
        elif hasattr(mem, "retrieve"):
            hits = mem.retrieve(q, top_k=5)  # type: ignore[arg-type]
        elif hasattr(mem, "query"):
            hits = mem.query(q, top_k=5)  # type: ignore[arg-type]
        else:
            return None
    except Exception:
        return None

    try:
        if not hits:
            return None
        lines: List[str] = []
        for h in hits[:5]:
            if isinstance(h, str):
                lines.append(h.strip())
            elif isinstance(h, dict):
                t = h.get("text") or h.get("content") or h.get("summary") or ""
                if t:
                    lines.append(str(t).strip())
        out = "\n- " + "\n- ".join([ln for ln in lines if ln][:5])
        return out.strip() if out.strip() else None
    except Exception:
        return None


def plan_for_veritas_agi(
    context: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    """
    VERITAS / AGI ベンチ用のメイン Planner（Worldステージ × LLM ハイブリッド版）。
    """
    ctx: Dict[str, Any] = context or {}

    # ★ まず simple QA なら即リターン
    if _is_simple_qa(query, ctx):
        try:
            world_snap_simple: Dict[str, Any] | None = world_model.snapshot("veritas_agi")
        except Exception:
            world_snap_simple = None
        return _simple_qa_plan(query=query, context=ctx, world_snap=world_snap_simple)

    # WorldModel snapshot
    try:
        world_snap: Dict[str, Any] | None = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = None

    stage = _infer_veritas_stage(world_snap)

    # step1 誤爆防止フラグ（prompt 側に伝える）
    wants_step1 = _wants_inventory_step(query, ctx)
    disallow_step1 = not wants_step1

    # MemoryOS（あれば使う・無ければ無視）
    memory_text: Optional[str] = None
    try:
        memory_text = _try_get_memory_snippet(query, ctx)
    except Exception:
        memory_text = None

    system_prompt = _build_system_prompt()

    world_for_prompt: Dict[str, Any] = dict(world_snap or {})
    world_for_prompt["stage"] = stage

    user_prompt = _build_user_prompt(
        query=query,
        context=ctx,
        world=world_for_prompt,
        memory_text=memory_text,
    )

    try:
        res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_messages=None,
            temperature=0.25,
            max_tokens=2000,
        )

        raw_text = res.get("text") if isinstance(res, dict) else str(res)

        # NOTE: あなたの実装に合わせて関数名を統一
        # 既存が _safe_json_extract ならそれを使う
        parsed = _safe_json_extract(raw_text)

        steps_obj: Any = None
        if isinstance(parsed, dict):
            steps_obj = parsed.get("steps")
        elif isinstance(parsed, list):
            steps_obj = parsed

        if isinstance(steps_obj, list) and len(steps_obj) > 0:
            original_steps = _normalize_steps_list(steps_obj, default_eta_hours=1.0, default_risk=0.1)
            steps = original_steps

            # disallow_step1 のときは step1 を落とす（ただし “空になったら戻す”）
            if disallow_step1:
                filtered = [s for s in original_steps if str(s.get("id") or "").lower() != "step1"]
                if filtered:
                    steps = filtered
                else:
                    logger.warning(
                        "PlannerOS: step1 filter would empty steps; keeping original LLM steps (safety + test compatibility)"
                    )
                    steps = original_steps

            return {
                "steps": steps,
                "raw": {
                    "parsed": parsed,
                    "text": raw_text,
                    "stage": stage,
                    "world_snapshot": world_snap or {},
                    "query": (query or "").strip(),
                    "memory_used": bool(memory_text),
                    "disallow_step1": bool(disallow_step1),
                },
                "meta": {
                    "stage": stage,
                    "query_type": "llm",
                },
                "source": "openai_llm",
            }

        logger.warning("PlannerOS: steps missing; fallback to stage plan")
        return _fallback_plan_for_stage(query, stage, world_snap)

    except Exception as e:
        logger.error("PlannerOS: ERROR in plan_for_veritas_agi: %r", e)
        # 例外時：まず stage_fallback。もしそれも失敗なら minimal fallback
        try:
            return _fallback_plan_for_stage(query, stage, world_snap)
        except Exception:
            return _fallback_plan(query, disallow_step1=disallow_step1)



# ============================
#  bench → 「コード変更タスク」変換（統合版）
# ============================

def _priority_from_risk_impact(risk: str | None, impact: str | None) -> str:
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
    bench: Optional[Dict[str, Any]] = None,
    world_state: Optional[Dict[str, Any]] = None,
    doctor_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    優先順位:
    0) bench に changes/tests が直接入っている場合 → それを信頼して「純ロジック」で tasks 化（テスト互換・決定論）
    1) それ以外 → code_planner.generate_code_change_plan が使える場合はそれを優先
    """
    bench = bench or {}
    bench_id = bench.get("bench_id") or "agi_veritas_self_hosting"

    # ---- (0) bench直読みがあるなら code_planner を使わない（重要） ----
    bench_changes = bench.get("changes")
    bench_tests = bench.get("tests")
    has_inline_changes = isinstance(bench_changes, list) and len(bench_changes) > 0
    has_inline_tests = isinstance(bench_tests, list) and len(bench_tests) > 0
    prefer_inline = has_inline_changes or has_inline_tests

    # ---- (A) code_planner 優先経路（ただし prefer_inline のときはスキップ） ----
    if not prefer_inline:
        try:
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

                tasks.append(
                    {
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
                )

            return {
                "bench_id": bench_id,
                "plan": plan_dict,
                "tasks": tasks,
            }

        except Exception:
            # code_planner が落ちたら純ロジックへ
            pass

    # ---- (B) bench直読みの純ロジック経路 ----
    world_snap = bench.get("world_snapshot") or {}
    doctor_summary = bench.get("doctor_summary") or {}
    bench_summary = bench.get("bench_summary") or {}

    changes = bench.get("changes") or []
    tests = bench.get("tests") or []

    if world_state is None:
        try:
            world_state = world_model.get_state()
        except Exception:
            world_state = None

    dr = doctor_report or {}
    dr_issues = dr.get("issues") or doctor_summary.get("top_issues") or []

    tasks2: List[Dict[str, Any]] = []

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

        tasks2.append(
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

    for idx, t in enumerate(tests, start=1):
        if not isinstance(t, dict):
            continue
        title = t.get("title") or "テストケースの追加"
        desc = t.get("description") or ""
        kind = t.get("kind") or "unit"
        tasks2.append(
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

        tasks2.append(
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

    meta: Dict[str, Any] = {
        "bench_id": bench_id,
        "has_bench": bool(bench),
        "has_doctor_report": bool(dr),
        "progress": None,
        "decision_count": None,
        "doctor_issue_count": len(dr_issues),
        "source": "planner.generate_code_tasks",
        "prefer_inline_bench": bool(prefer_inline),
    }

    try:
        if world_state and isinstance(world_state, dict):
            veritas = (world_state.get("veritas") or {})
            meta["progress"] = float(veritas.get("progress", 0.0))
            meta["decision_count"] = int(veritas.get("decision_count", 0))
    except Exception:
        pass

    return {
        "tasks": tasks2,
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
    _ = context or {}

    q = (query or "").strip()
    chosen_title = (chosen or {}).get("title") or "決定されたアクション"
    chosen_desc = (chosen or {}).get("description") or ""

    steps: List[Dict[str, Any]] = []

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

    steps.append(
        {
            "id": "log",
            "title": "実行内容のログ化",
            "detail": "実行した内容・使った判断基準・気づきをVERITASログ/メモに記録する。（将来の学習用）",
            "priority": 4,
            "eta_minutes": 5,
        }
    )

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
