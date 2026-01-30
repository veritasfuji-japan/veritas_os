# veritas_os/core/types.py
# -*- coding: utf-8 -*-
"""
VERITAS OS 共通型定義モジュール

プロジェクト全体で使用される TypedDict、Protocol、型エイリアスを定義。
型安全性を高め、IDE補完とドキュメント生成を改善する。

使用方法:
    from veritas_os.core.types import (
        ToolResult,
        FujiDecisionDict,
        OptionDict,
        EvidenceDict,
        DecideResult,
    )
"""
from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Sequence,
    TypedDict,
    Union,
    runtime_checkable,
)


# =============================================================================
# 基本型エイリアス
# =============================================================================

# JSON互換の値
JsonValue = Union[str, int, float, bool, None, List["JsonValue"], Dict[str, "JsonValue"]]

# ユーザーID
UserId = str

# リクエストID
RequestId = str

# タイムスタンプ (ISO 8601形式)
ISOTimestamp = str


# =============================================================================
# ツール関連
# =============================================================================

class ToolResult(TypedDict, total=False):
    """環境ツールの実行結果"""
    ok: bool
    results: List[Dict[str, Any]]
    error: Optional[str]
    elapsed_ms: float


class WebSearchResult(TypedDict, total=False):
    """Web検索の個別結果"""
    title: str
    url: str
    snippet: str
    score: float


class WebSearchResponse(TypedDict, total=False):
    """Web検索ツールのレスポンス"""
    ok: bool
    results: List[WebSearchResult]
    query: str
    error: Optional[str]


# =============================================================================
# オプション / 選択肢
# =============================================================================

class OptionDict(TypedDict, total=False):
    """決定の選択肢"""
    id: str
    title: str
    description: str
    score: float
    rationale: str
    source: str


class ChosenDict(TypedDict, total=False):
    """選択された決定"""
    id: str
    title: str
    description: str
    rationale: str
    confidence: float
    action: str


# =============================================================================
# エビデンス
# =============================================================================

class EvidenceDict(TypedDict, total=False):
    """決定を裏付けるエビデンス"""
    id: str
    kind: Literal["memory", "web", "world", "tool", "user"]
    text: str
    source: str
    relevance: float
    timestamp: ISOTimestamp
    meta: Dict[str, Any]


# =============================================================================
# FUJI Gate
# =============================================================================

# FUJI内部ステータス
FujiInternalStatus = Literal["allow", "allow_with_warning", "needs_human_review", "deny"]

# FUJI外部ステータス (API向け)
FujiDecisionStatus = Literal["allow", "hold", "deny"]

# v1互換ステータス
FujiV1Status = Literal["allow", "rejected", "modify"]


class FujiViolation(TypedDict, total=False):
    """FUJIポリシー違反"""
    rule_id: str
    rule_name: str
    severity: Literal["low", "medium", "high", "critical"]
    description: str
    matched_text: str


class FujiFollowup(TypedDict, total=False):
    """FUJI追加調査アクション"""
    action: str
    reason: str
    priority: Literal["low", "medium", "high"]


class FujiDecisionDict(TypedDict, total=False):
    """FUJI Gate の決定結果"""
    status: FujiInternalStatus
    decision_status: FujiDecisionStatus
    risk_score: float
    reasons: List[str]
    violations: List[FujiViolation]
    modifications: List[str]
    followups: List[FujiFollowup]
    rejection_reason: Optional[str]
    action: str
    timestamp: ISOTimestamp


class FujiV1Result(TypedDict, total=False):
    """FUJI v1互換レスポンス"""
    status: FujiV1Status
    reasons: List[str]
    violations: List[str]
    risk: float
    modifications: List[str]
    action: str


# =============================================================================
# Safety Head
# =============================================================================

class SafetyHeadResultDict(TypedDict, total=False):
    """Safety Headの分析結果"""
    risk_score: float
    categories: List[str]
    rationale: str
    model: str
    raw: Dict[str, Any]


# =============================================================================
# メモリ
# =============================================================================

class MemoryEntry(TypedDict, total=False):
    """メモリエントリ"""
    id: str
    kind: Literal["episodic", "semantic", "skills", "doc", "plan"]
    text: str
    embedding: List[float]
    tags: List[str]
    meta: Dict[str, Any]
    created_at: ISOTimestamp
    updated_at: ISOTimestamp
    user_id: Optional[UserId]


class MemorySearchHit(TypedDict, total=False):
    """メモリ検索結果"""
    id: str
    text: str
    kind: str
    similarity: float
    meta: Dict[str, Any]


class MemorySearchResponse(TypedDict, total=False):
    """メモリ検索レスポンス"""
    ok: bool
    hits: List[MemorySearchHit]
    count: int
    query: str
    error: Optional[str]


# =============================================================================
# Value Core / Trust
# =============================================================================

class TrustLogEntry(TypedDict, total=False):
    """TrustLogエントリ"""
    id: str
    timestamp: ISOTimestamp
    user_id: UserId
    request_id: RequestId
    action: str
    score: float
    note: str
    source: str
    hash: str
    prev_hash: str
    extra: Dict[str, Any]


class ValueCoreResult(TypedDict, total=False):
    """Value Coreの評価結果"""
    telos_score: float
    alignment_score: float
    value_ema: float
    rationale: str


# =============================================================================
# Debate / Critique
# =============================================================================

class DebateViewpoint(TypedDict, total=False):
    """Debateの視点"""
    role: Literal["pro", "con", "third_party", "synthesizer"]
    argument: str
    evidence: List[str]
    confidence: float


class CritiquePoint(TypedDict, total=False):
    """批評ポイント"""
    category: str
    description: str
    severity: Literal["low", "medium", "high"]
    suggestion: str


# =============================================================================
# Planner
# =============================================================================

class PlanStep(TypedDict, total=False):
    """計画ステップ"""
    step_id: str
    action: str
    description: str
    dependencies: List[str]
    estimated_duration: Optional[str]
    tools_required: List[str]


class PlanResult(TypedDict, total=False):
    """Plannerの結果"""
    plan_id: str
    goal: str
    steps: List[PlanStep]
    total_steps: int
    confidence: float
    rationale: str


# =============================================================================
# World State
# =============================================================================

class WorldStateDict(TypedDict, total=False):
    """ワールド状態"""
    timestamp: ISOTimestamp
    entities: Dict[str, Dict[str, Any]]
    relations: List[Dict[str, Any]]
    facts: List[str]
    user_context: Dict[str, Any]


# =============================================================================
# 決定パイプライン
# =============================================================================

class DecideContext(TypedDict, total=False):
    """決定コンテキスト"""
    user_id: UserId
    session_id: str
    query: str
    options: List[OptionDict]
    min_evidence: int
    max_options: int
    persona: Dict[str, Any]
    world_state: WorldStateDict
    extra: Dict[str, Any]


class DecideResult(TypedDict, total=False):
    """決定パイプラインの結果"""
    ok: bool
    request_id: RequestId
    chosen: ChosenDict
    alternatives: List[OptionDict]
    options: List[OptionDict]
    evidence: List[EvidenceDict]
    critique: List[CritiquePoint]
    debate: List[DebateViewpoint]
    fuji: FujiDecisionDict
    telos_score: float
    trust_log: Optional[TrustLogEntry]
    elapsed_ms: float
    error: Optional[str]
    warn: Optional[str]


# =============================================================================
# API リクエスト/レスポンス (内部用)
# =============================================================================

class DecideRequestDict(TypedDict, total=False):
    """決定リクエスト (内部辞書形式)"""
    context: DecideContext
    query: str
    options: List[OptionDict]
    min_evidence: int


class MemoryPutRequest(TypedDict, total=False):
    """メモリ書き込みリクエスト"""
    user_id: UserId
    key: str
    value: Dict[str, Any]
    kind: Literal["semantic", "episodic", "skills", "doc", "plan"]
    text: str
    tags: List[str]
    meta: Dict[str, Any]


class MemoryGetRequest(TypedDict, total=False):
    """メモリ取得リクエスト"""
    user_id: UserId
    key: str


# =============================================================================
# Protocol定義 (構造的部分型)
# =============================================================================

@runtime_checkable
class SupportsSearch(Protocol):
    """検索機能を持つオブジェクト"""
    def search(
        self,
        query: str,
        *,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
        user_id: Optional[str] = None,
    ) -> List[MemorySearchHit]:
        ...


@runtime_checkable
class SupportsPut(Protocol):
    """書き込み機能を持つオブジェクト"""
    def put(
        self,
        user_id: str,
        key: str,
        value: Dict[str, Any],
    ) -> None:
        ...


@runtime_checkable
class SupportsGet(Protocol):
    """取得機能を持つオブジェクト"""
    def get(
        self,
        user_id: str,
        key: str,
    ) -> Optional[Dict[str, Any]]:
        ...


@runtime_checkable
class MemoryStoreProtocol(SupportsSearch, SupportsPut, SupportsGet, Protocol):
    """メモリストアの完全なプロトコル"""
    pass


@runtime_checkable
class LLMClientProtocol(Protocol):
    """LLMクライアントのプロトコル"""
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        ...


# =============================================================================
# 型ガード関数
# =============================================================================

def is_option_dict(obj: Any) -> bool:
    """OptionDict形式かどうかを判定"""
    if not isinstance(obj, dict):
        return False
    return "title" in obj or "id" in obj


def is_evidence_dict(obj: Any) -> bool:
    """EvidenceDict形式かどうかを判定"""
    if not isinstance(obj, dict):
        return False
    return "text" in obj and ("kind" in obj or "source" in obj)


def is_fuji_decision(obj: Any) -> bool:
    """FujiDecisionDict形式かどうかを判定"""
    if not isinstance(obj, dict):
        return False
    return "status" in obj and obj.get("status") in (
        "allow", "allow_with_warning", "needs_human_review", "deny",
        "rejected", "modify", "hold"
    )


def ensure_option_dict(obj: Any, default_id: str = "opt_0") -> OptionDict:
    """任意のオブジェクトをOptionDictに変換"""
    if obj is None:
        return {"id": default_id, "title": "", "description": "", "score": 1.0}
    if isinstance(obj, dict):
        return {
            "id": obj.get("id") or default_id,
            "title": obj.get("title") or obj.get("text") or str(obj),
            "description": obj.get("description") or "",
            "score": float(obj.get("score", 1.0)),
        }
    return {"id": default_id, "title": str(obj), "description": "", "score": 1.0}


def ensure_evidence_list(obj: Any) -> List[EvidenceDict]:
    """任意のオブジェクトをEvidenceのリストに変換"""
    if obj is None:
        return []
    if isinstance(obj, list):
        return [
            {
                "id": e.get("id", f"ev_{i}"),
                "kind": e.get("kind", "unknown"),
                "text": e.get("text", str(e)),
                "source": e.get("source", ""),
                "relevance": float(e.get("relevance", 0.5)),
            }
            for i, e in enumerate(obj)
            if isinstance(e, dict)
        ]
    return []


# =============================================================================
# エクスポート
# =============================================================================

__all__ = [
    # 型エイリアス
    "JsonValue",
    "UserId",
    "RequestId",
    "ISOTimestamp",
    # ツール
    "ToolResult",
    "WebSearchResult",
    "WebSearchResponse",
    # オプション
    "OptionDict",
    "ChosenDict",
    # エビデンス
    "EvidenceDict",
    # FUJI
    "FujiInternalStatus",
    "FujiDecisionStatus",
    "FujiV1Status",
    "FujiViolation",
    "FujiFollowup",
    "FujiDecisionDict",
    "FujiV1Result",
    "SafetyHeadResultDict",
    # メモリ
    "MemoryEntry",
    "MemorySearchHit",
    "MemorySearchResponse",
    # Value/Trust
    "TrustLogEntry",
    "ValueCoreResult",
    # Debate/Critique
    "DebateViewpoint",
    "CritiquePoint",
    # Planner
    "PlanStep",
    "PlanResult",
    # World
    "WorldStateDict",
    # 決定パイプライン
    "DecideContext",
    "DecideResult",
    "DecideRequestDict",
    # メモリAPI
    "MemoryPutRequest",
    "MemoryGetRequest",
    # Protocol
    "SupportsSearch",
    "SupportsPut",
    "SupportsGet",
    "MemoryStoreProtocol",
    "LLMClientProtocol",
    # 型ガード
    "is_option_dict",
    "is_evidence_dict",
    "is_fuji_decision",
    "ensure_option_dict",
    "ensure_evidence_list",
]
