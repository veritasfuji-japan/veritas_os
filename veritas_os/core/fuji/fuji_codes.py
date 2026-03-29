# veritas_os/core/fuji_codes.py
# -*- coding: utf-8 -*-
"""
FUJI Standard Codes registry and rejection response builders.

This module defines the FUJI error code system (F-1xxx to F-4xxx),
validates registry consistency, and builds the standard REJECTED JSON
response payload required by FUJI Safety Gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
import re

FUJI_CODE_PATTERN = re.compile(r"^F-[1-4]\d{3}$")


class FujiLayer(str, Enum):
    """FUJI error layer mapping."""

    DATA_EVIDENCE = "Data & Evidence"
    LOGIC_DEBATE = "Logic & Debate"
    VALUE_POLICY = "Value & Policy"
    SAFETY_SECURITY = "Safety & Security"


class FujiSeverity(str, Enum):
    """FUJI severity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FujiAction(str, Enum):
    """FUJI feedback action codes."""

    RE_DEBATE = "RE-DEBATE"
    RE_CRITIQUE = "RE-CRITIQUE"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    REWRITE_PLAN = "REWRITE_PLAN"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True)
class FujiError:
    """FUJI error information."""

    code: str
    message: str
    detail: str
    layer: FujiLayer
    severity: FujiSeverity
    blocking: bool


@dataclass(frozen=True)
class FujiFeedback:
    """FUJI feedback instruction."""

    action: FujiAction
    hint: str


@dataclass(frozen=True)
class FujiGateResponse:
    """Standard FUJI gate response."""

    status: str
    gate: str
    error: Optional[FujiError]
    feedback: Optional[FujiFeedback]
    trust_log_id: str


@dataclass(frozen=True)
class FujiRegistryEntry:
    """Registry entry for FUJI codes."""

    error: FujiError
    feedback: FujiFeedback


_LAYER_BY_PREFIX: Dict[str, FujiLayer] = {
    "1": FujiLayer.DATA_EVIDENCE,
    "2": FujiLayer.LOGIC_DEBATE,
    "3": FujiLayer.VALUE_POLICY,
    "4": FujiLayer.SAFETY_SECURITY,
}


FUJI_REGISTRY: Dict[str, FujiRegistryEntry] = {
    "F-1002": FujiRegistryEntry(
        error=FujiError(
            code="F-1002",
            message="Insufficient Evidence",
            detail="根拠が結論を支えるには不十分です。",
            layer=FujiLayer.DATA_EVIDENCE,
            severity=FujiSeverity.MEDIUM,
            blocking=False,
        ),
        feedback=FujiFeedback(
            action=FujiAction.REQUEST_EVIDENCE,
            hint="判断に必要な一次情報・根拠を追加し、出典と妥当性を明示してください。",
        ),
    ),
    "F-1005": FujiRegistryEntry(
        error=FujiError(
            code="F-1005",
            message="Inconsistent Data",
            detail="証拠Aと証拠Bに解消不能な矛盾があります。",
            layer=FujiLayer.DATA_EVIDENCE,
            severity=FujiSeverity.HIGH,
            blocking=True,
        ),
        feedback=FujiFeedback(
            action=FujiAction.RE_CRITIQUE,
            hint="矛盾する証拠の優先度と原因を再評価し、整合するデータに置き換えてください。",
        ),
    ),
    "F-2101": FujiRegistryEntry(
        error=FujiError(
            code="F-2101",
            message="Critique Unresolved",
            detail="Critiqueで指摘されたリスクがPlanに反映されていません。",
            layer=FujiLayer.LOGIC_DEBATE,
            severity=FujiSeverity.HIGH,
            blocking=True,
        ),
        feedback=FujiFeedback(
            action=FujiAction.RE_DEBATE,
            hint="指摘されたリスクを反映した上で議論を再実行し、修正案を提示してください。",
        ),
    ),
    "F-2203": FujiRegistryEntry(
        error=FujiError(
            code="F-2203",
            message="Logic Leap",
            detail="根拠から結論までの推論に飛躍があります。",
            layer=FujiLayer.LOGIC_DEBATE,
            severity=FujiSeverity.MEDIUM,
            blocking=False,
        ),
        feedback=FujiFeedback(
            action=FujiAction.RE_CRITIQUE,
            hint="推論の前提と論理の連結を明示し、欠落したステップを補完してください。",
        ),
    ),
    "F-3001": FujiRegistryEntry(
        error=FujiError(
            code="F-3001",
            message="ValueCore Mismatch",
            detail="優先価値より別価値を優先しておりポリシー違反です。",
            layer=FujiLayer.VALUE_POLICY,
            severity=FujiSeverity.HIGH,
            blocking=True,
        ),
        feedback=FujiFeedback(
            action=FujiAction.REWRITE_PLAN,
            hint="優先価値（例: 安全性）を最上位に置いた計画へ修正してください。",
        ),
    ),
    "F-3008": FujiRegistryEntry(
        error=FujiError(
            code="F-3008",
            message="Ethical Boundary",
            detail="行動が倫理/規定の境界線を越えています。",
            layer=FujiLayer.VALUE_POLICY,
            severity=FujiSeverity.HIGH,
            blocking=True,
        ),
        feedback=FujiFeedback(
            action=FujiAction.HUMAN_REVIEW,
            hint="行動案を停止し、倫理基準に照らした再評価と人間レビューを依頼してください。",
        ),
    ),
    "F-4001": FujiRegistryEntry(
        error=FujiError(
            code="F-4001",
            message="Prompt Injection Suspected",
            detail="プロンプトインジェクションの疑いがあります。",
            layer=FujiLayer.SAFETY_SECURITY,
            severity=FujiSeverity.HIGH,
            blocking=True,
        ),
        feedback=FujiFeedback(
            action=FujiAction.HUMAN_REVIEW,
            hint="入力を安全に再評価し、ポリシーを無視する指示を除去してください。",
        ),
    ),
    "F-4003": FujiRegistryEntry(
        error=FujiError(
            code="F-4003",
            message="Sensitive Info Leak Risk",
            detail="個人情報/機密情報の漏洩リスクがあります。",
            layer=FujiLayer.SAFETY_SECURITY,
            severity=FujiSeverity.MEDIUM,
            blocking=True,
        ),
        feedback=FujiFeedback(
            action=FujiAction.REWRITE_PLAN,
            hint="個人情報を削除またはマスクし、安全な範囲に修正してください。",
        ),
    ),
}


def _enforce_registry_rules(code: str, entry: FujiRegistryEntry) -> None:
    if not FUJI_CODE_PATTERN.match(code):
        raise ValueError(f"invalid FUJI code format: {code}")

    prefix = code.split("-", 1)[1][0]
    expected_layer = _LAYER_BY_PREFIX.get(prefix)
    if entry.error.layer != expected_layer:
        raise ValueError(f"layer mismatch for {code}: {entry.error.layer}")

    if entry.error.severity == FujiSeverity.HIGH and not entry.error.blocking:
        raise ValueError(f"severity HIGH requires blocking=True for {code}")

    if code in {"F-4001", "F-4003"}:
        if entry.error.severity == FujiSeverity.LOW:
            raise ValueError(f"{code} must be >= MEDIUM severity")
        if not entry.error.blocking:
            raise ValueError(f"{code} must be blocking")

    if code == "F-2101" and entry.feedback.action != FujiAction.RE_DEBATE:
        raise ValueError("F-2101 feedback.action must be RE-DEBATE")


def _validate_registry() -> None:
    for code, entry in FUJI_REGISTRY.items():
        _enforce_registry_rules(code, entry)


_validate_registry()


def validate_fuji_code(code: str) -> None:
    """
    Validate that a FUJI code is correctly formatted and registered.
    """
    if not FUJI_CODE_PATTERN.match(code):
        raise ValueError(f"invalid FUJI code format: {code}")
    if code not in FUJI_REGISTRY:
        raise ValueError(f"unknown FUJI code: {code}")


def build_fuji_rejection(
    code: str,
    trust_log_id: str,
    detail_override: Optional[str] = None,
    hint_override: Optional[str] = None,
) -> dict:
    """
    Build the standard REJECTED JSON response for FUJI Safety Gate.
    """
    validate_fuji_code(code)
    entry = FUJI_REGISTRY[code]

    detail = detail_override if detail_override is not None else entry.error.detail
    hint = hint_override if hint_override is not None else entry.feedback.hint

    error_payload = {
        "code": entry.error.code,
        "message": entry.error.message,
        "detail": detail,
        "layer": entry.error.layer.value,
        "severity": entry.error.severity.value,
        "blocking": entry.error.blocking,
    }
    feedback_payload = {
        "action": entry.feedback.action.value,
        "hint": hint,
    }

    response = FujiGateResponse(
        status="REJECTED",
        gate="FUJI_SAFETY_GATE_v2",
        error=entry.error,
        feedback=entry.feedback,
        trust_log_id=str(trust_log_id),
    )

    return {
        "status": response.status,
        "gate": response.gate,
        "error": error_payload,
        "feedback": feedback_payload,
        "trust_log_id": response.trust_log_id,
    }


__all__ = [
    "FujiLayer",
    "FujiSeverity",
    "FujiAction",
    "FujiError",
    "FujiFeedback",
    "FujiGateResponse",
    "FUJI_REGISTRY",
    "validate_fuji_code",
    "build_fuji_rejection",
]
