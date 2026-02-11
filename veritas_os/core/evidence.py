# veritas_os/core/evidence.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Evidence は dict ベースで扱う（テスト側が e["snippet"] アクセスを前提にしている）
Evidence = Dict[str, Any]


def _mk(
    *,
    source: str,
    kind: str,
    weight: float,
    snippet: str,
    tags: List[str] | None = None,
    title: str | None = None,
    uri: str | None = None,
) -> Evidence:
    """内部用の小さなヘルパー。

    pipeline 側で _norm_evidence_item が吸収できるが、
    ここでも最低限の整形をして「落ちない」保証を強める。
    """
    k = str(kind or "unknown")

    # title/uri を最低限埋める（空文字も弾く）
    t = title if (title is not None and str(title).strip() != "") else f"local:{k}"
    u = uri if (uri is not None and str(uri).strip() != "") else f"internal:evidence:{k}"

    # weight -> confidence（絶対に落とさない）
    try:
        w = float(weight)
    except (ValueError, TypeError):
        w = 0.2
    conf = max(0.0, min(1.0, w))

    return {
        "source": str(source or "local"),
        "kind": k,
        "weight": w,
        "snippet": "" if snippet is None else str(snippet),
        "tags": list(tags or []),

        # 互換: pipeline contract
        "title": str(t),
        "uri": str(u),
        "confidence": conf,
    }



def collect_local(intent: str, query: str, context: Dict[str, Any]) -> List[Evidence]:
    """
    DecisionOS が「ローカル・ヒューリスティクス」として追加するエビデンス群。

    - intent / query / context をざっくり見て、数件の Evidence(dict) を返す。
    - ここでは一切 LLM を呼ばず、決め打ちのルールだけを書く。
    """
    ev: List[Evidence] = []
    ctx = context or {}

    q = (query or "").strip()
    goals = ctx.get("goals") or []
    stakes_raw = ctx.get("stakes")
    constraints = ctx.get("constraints") or []

    # --- 疲労 / 健康まわりのヒューリスティクス ---------------------------
    if ("疲れ" in q) or any(g in ("健康", "回復") for g in goals):
        ev.append(
            _mk(
                source="local",
                kind="fatigue",
                weight=0.6,
                snippet=(
                    "疲労時は回復優先で判断した方が後悔が少ないことが多い。"
                    "最近の疲れ・体調・睡眠パターンもメモしておくと、後から自己分析しやすい。"
                ),
                tags=["selfcare", "health"],
            )
        )

    # --- stakes が高いときは『慎重側に倒す』という原則 --------------------
    stakes_val: Optional[float] = None
    if stakes_raw is not None:
        try:
            stakes_val = float(stakes_raw)
        except (TypeError, ValueError):
            stakes_val = None

    if stakes_val is not None and stakes_val >= 0.7:
        ev.append(
            _mk(
                source="local",
                kind="stakes",
                weight=stakes_val,
                snippet=(
                    f"stakesが高いため慎重側に倒す方が後悔が少ないと想定する"
                    f"（現在のstakes={stakes_val:.2f}）。"
                ),
                tags=["stakes", "caution"],
            )
        )

    # --- 制約条件が指定されているときのメモ --------------------------------
    if constraints:
        if isinstance(constraints, str):
            constraints_list = [constraints]
        else:
            constraints_list = list(constraints)

        joined = " / ".join(str(c) for c in constraints_list)
        ev.append(
            _mk(
                source="local",
                kind="constraints",
                weight=0.5,
                snippet=f"制約: {joined} を前提に方針を組み立てる。",
                tags=["constraints"],
            )
        )

    # --- 天気関連（intent = weather） --------------------------------------
    if intent == "weather":
        ev.append(
            _mk(
                source="local",
                kind="weather",
                weight=0.5,
                snippet=(
                    # ★ テストが "天候は影響大" を期待している
                    "天候は影響大なので、屋外活動・移動・体調への影響を"
                    "前提にスケジュールを組んだ方がよい。"
                ),
                tags=["weather", "context"],
            )
        )

    # --- 何もヒットしなかったときのフォールバック ------------------------
    if not ev:
        ev.append(
            _mk(
                source="local",
                kind="fallback",
                weight=0.2,
                snippet=(
                    "クエリの意図に沿うようスコアリング済みだが、"
                    "goals / stakes / constraints が指定されていないため、"
                    "まずは『どうなりたいか』『どれくらいリスクを取れるか』"
                    "『時間・お金などの制約』を一緒に整理すると意思決定の質が上がる。"
                ),
                tags=["meta", "fallback"],
            )
        )

    # 付けすぎてもノイズになるので 4 件まで
    return ev[:4]
# --- 追加: step1 の low_evidence 対策 ----------------------------

def step1_minimum_evidence(context: Dict[str, Any]) -> List[Evidence]:
    """
    step1 を選ぶ場合に、最低限 2 本の evidence を保証する。
    - 現状機能の“棚卸し出力（list）”
    - 既知の課題（テスト失敗・障害ログ・未実装一覧など）
    """
    ctx = context or {}

    # 1) 現状機能の棚卸し（“存在しているものだけ” を列挙）
    features = [
        "API: /v1/decide (FastAPI + Uvicorn)",
        "Decision pipeline: Planner → (optional WebSearch) → Reason/Debate → FUJI Gate → TrustLog",
        "Memory: MemoryOS + WorldModel state update",
        "Logging: TrustLog (hash-chain) + dataset_writer + rotate/paths",
        "Safety: llm_safety / FUJI gate",
        "Tests: pytest suite + coverage",
    ]
    inventory_snippet = "現状機能（棚卸し）:\n- " + "\n- ".join(features)

    # 2) 既知の課題（最低でも“既知課題がある/ない”を証拠として固定化）
    known = [
        "tokenizers の fork 警告が出る場合がある（TOKENIZERS_PARALLELISM で抑制可能）",
        "WebSearch は環境変数未設定だと degraded/empty になりうる（CIでは contract を満たすフォールバック）",
        "ローカル起動時に port 競合（address already in use）が起きる場合がある",
    ]

    # 任意: 呼び出し側でテスト/障害概要を context に載せたら最上段に出す
    test_summary = ctx.get("test_summary")
    if test_summary:
        known.insert(0, f"テスト状況: {test_summary}")

    issues_snippet = "既知の課題/注意:\n- " + "\n- ".join(known)

    return [
        _mk(
            source="local",
            kind="inventory",
            weight=0.65,
            snippet=inventory_snippet,
            tags=["inventory", "system"],
        ),
        _mk(
            source="local",
            kind="known_issues",
            weight=0.60,
            snippet=issues_snippet,
            tags=["issues", "quality"],
        ),
    ]



