# veritas_os/core/pipeline_types.py
# -*- coding: utf-8 -*-
"""
Pipeline shared types and constants.

This module defines:
- PipelineContext: mutable state flowing through all pipeline stages
- Pipeline constants (magic numbers consolidated)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# =========================================================
# Pipeline constants (magic numbers consolidated)
# =========================================================
MIN_MEMORY_SIMILARITY: float = 0.30        # メモリ検索の最小類似度
DEFAULT_CONFIDENCE: float = 0.55           # デフォルト信頼度（web_search fallback等）
DOC_MIN_CONFIDENCE: float = 0.75           # ドキュメント証拠の最小信頼度
TELOS_THRESHOLD_MIN: float = 0.35          # テロス閾値の下限
TELOS_THRESHOLD_MAX: float = 0.75          # テロス閾値の上限
HIGH_RISK_THRESHOLD: float = 0.90          # 高リスク判定閾値
BASE_TELOS_THRESHOLD: float = 0.55         # 基本テロススコア閾値


@dataclass
class PipelineContext:
    """Mutable state shared across all pipeline stages.

    Created by :func:`pipeline_inputs.normalize_pipeline_inputs` and
    threaded through every stage so that each function can read and
    update the relevant slice of state.
    """

    # --- Parsed inputs (set once in normalize_pipeline_inputs) ---
    body: Dict[str, Any] = field(default_factory=dict)
    query: str = ""
    user_id: str = "anon"
    request_id: str = ""
    fast_mode: bool = False
    replay_mode: bool = False
    mock_external_apis: bool = False
    seed: int = 0
    min_ev: int = 1
    started_at: float = field(default_factory=time.time)
    is_veritas_query: bool = False
    context: Dict[str, Any] = field(default_factory=dict)

    # --- Response extras (accumulated across stages) ---
    response_extras: Dict[str, Any] = field(default_factory=dict)

    # --- Evidence ---
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    web_evidence: List[Dict[str, Any]] = field(default_factory=list)
    retrieved: List[Dict[str, Any]] = field(default_factory=list)

    # --- Decision outputs ---
    raw: Dict[str, Any] = field(default_factory=dict)
    chosen: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    input_alts: List[Dict[str, Any]] = field(default_factory=list)
    explicit_options: List[Dict[str, Any]] = field(default_factory=list)

    # --- Subsystem outputs ---
    critique: Dict[str, Any] = field(default_factory=dict)
    debate: List[Any] = field(default_factory=list)
    telos: float = 0.0
    fuji_dict: Dict[str, Any] = field(default_factory=dict)
    plan: Dict[str, Any] = field(
        default_factory=lambda: {"steps": [], "raw": None, "source": "fallback"},
    )
    values_payload: Dict[str, Any] = field(
        default_factory=lambda: {
            "scores": {},
            "total": 0.0,
            "top_factors": [],
            "rationale": "",
        },
    )

    # --- Self-healing ---
    healing_attempts: List[Dict[str, Any]] = field(default_factory=list)
    healing_stop_reason: Optional[str] = None

    # --- Gate ---
    decision_status: str = "allow"
    rejection_reason: Optional[str] = None
    modifications: List[Any] = field(default_factory=list)

    # --- Continuation runtime (shadow / observe / enforce) ---
    continuation_snapshot: Optional[Dict[str, Any]] = None
    continuation_receipt: Optional[Dict[str, Any]] = None
    continuation_enforcement_events: Optional[List[Dict[str, Any]]] = None
    continuation_enforcement_halt: bool = False

    # --- Stage flags ---
    _should_run_web: bool = False

    # --- Computed values ---
    effective_risk: float = 0.0
    value_ema: float = 0.5
    telos_threshold: float = BASE_TELOS_THRESHOLD
