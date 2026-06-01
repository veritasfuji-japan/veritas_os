"""FUJI policy diff replay and canary rollout utilities.

This module provides P0-3 controls described in the code review:
- deterministic A/B replay against old/new policies
- allow/hold/deny transition metrics
- false-positive / false-negative policy-regression estimates
- deterministic canary assignment by request id

The implementation is scoped to FUJI policy evaluation only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

from veritas_os.core import fuji

_ALLOWED_DECISIONS = {"allow", "hold", "deny"}
DEFAULT_FALSE_NEGATIVE_PROMOTION_THRESHOLD = 0.0
PROMOTION_BLOCKED_METRICS_UNAVAILABLE = "promotion_blocked_metrics_unavailable"


@dataclass(frozen=True)
class CanaryPromotionGateResult:
    """Promotion decision derived from canary replay safety metrics.

    False negatives are safety-critical because they mean the stable policy
    would HOLD or DENY while the canary policy would ALLOW. High-risk
    migrations, including negation/refusal-context category moves, should
    treat this gate as a promotion blocker rather than advisory telemetry.
    """

    allowed: bool
    reason: str
    false_negative_rate: float
    false_negative_threshold: float
    change_rate: float | None
    false_negatives: int
    samples_checked: int


@dataclass(frozen=True)
class PolicyReplaySample:
    """Single replay sample used for old/new policy comparison."""

    sample_id: str
    risk: float
    categories: List[str]
    stakes: float = 0.5
    telos_score: float = 0.5
    expected_decision: Optional[str] = None


def _normalize_expected_decision(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    norm = str(value).strip().lower()
    return norm if norm in _ALLOWED_DECISIONS else None


def _evaluate_sample(sample: PolicyReplaySample, policy: Mapping[str, Any]) -> str:
    """Evaluate one sample through FUJI's policy rule engine.

    Fail-closed behavior:
        - invalid decision values fall back to ``hold``
        - unexpected evaluation errors fall back to ``deny``
    """
    try:
        result = fuji._apply_policy(  # pylint: disable=protected-access
            risk=float(sample.risk),
            categories=list(sample.categories),
            stakes=float(sample.stakes),
            telos_score=float(sample.telos_score),
            policy=dict(policy),
        )
    except (TypeError, ValueError, RuntimeError):
        return "deny"

    decision = str(result.get("decision_status", "hold")).lower()
    if decision not in _ALLOWED_DECISIONS:
        return "hold"
    return decision


def replay_policy_diff(
    samples: Iterable[PolicyReplaySample],
    stable_policy: Mapping[str, Any],
    canary_policy: Mapping[str, Any],
) -> Dict[str, Any]:
    """Replay identical samples against stable/canary FUJI policies.

    Args:
        samples: Input sample iterator for replay.
        stable_policy: Current production FUJI policy.
        canary_policy: Candidate FUJI policy.

    Returns:
        Aggregated metrics and per-sample outcomes.
    """
    transition_counter: Counter[str] = Counter()
    outcomes: List[Dict[str, Any]] = []

    total = 0
    changed = 0
    fp = 0
    fn = 0
    labeled = 0

    for sample in samples:
        total += 1
        before = _evaluate_sample(sample, stable_policy)
        after = _evaluate_sample(sample, canary_policy)
        expected = _normalize_expected_decision(sample.expected_decision)
        is_changed = before != after
        changed += int(is_changed)

        transition_counter[f"{before}->{after}"] += 1

        is_fp = False
        is_fn = False
        if before == "allow" and after in {"hold", "deny"}:
            fp += 1
            is_fp = True
        elif before in {"hold", "deny"} and after == "allow":
            fn += 1
            is_fn = True

        if expected is not None:
            labeled += 1

        outcomes.append(
            {
                "sample_id": sample.sample_id,
                "stable": before,
                "canary": after,
                "changed": is_changed,
                "expected": expected,
                "false_positive": is_fp,
                "false_negative": is_fn,
            }
        )

    change_rate = (changed / total) if total else 0.0
    fp_rate = (fp / total) if total else 0.0
    fn_rate = (fn / total) if total else 0.0

    return {
        "total": total,
        "samples_checked": total,
        "changed": changed,
        "change_rate": round(change_rate, 6),
        "false_positive": fp,
        "false_negative": fn,
        "false_positive_rate": round(fp_rate, 6),
        "false_negative_rate": round(fn_rate, 6),
        "labeled": labeled,
        "transitions": dict(sorted(transition_counter.items())),
        "outcomes": outcomes,
    }


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonnegative_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def evaluate_canary_promotion_gate(
    diff_result: Any,
    *,
    false_negative_threshold: float = DEFAULT_FALSE_NEGATIVE_PROMOTION_THRESHOLD,
) -> CanaryPromotionGateResult:
    """Evaluate whether canary policy replay metrics permit promotion.

    Promotion fails closed when metrics are unavailable or malformed. A false
    negative is a permissive regression where the stable policy would HOLD or
    DENY but the canary policy would ALLOW.

    Args:
        diff_result: Result produced by :func:`replay_policy_diff`.
        false_negative_threshold: Maximum tolerated false-negative rate.

    Returns:
        Explicit canary promotion decision and the safety metrics used.
    """
    threshold = _finite_float(false_negative_threshold)
    if threshold is None or threshold < 0.0:
        threshold = DEFAULT_FALSE_NEGATIVE_PROMOTION_THRESHOLD

    blocked_result = CanaryPromotionGateResult(
        allowed=False,
        reason=PROMOTION_BLOCKED_METRICS_UNAVAILABLE,
        false_negative_rate=0.0,
        false_negative_threshold=threshold,
        change_rate=None,
        false_negatives=0,
        samples_checked=0,
    )

    if not isinstance(diff_result, Mapping):
        return blocked_result

    false_negative_rate = _finite_float(diff_result.get("false_negative_rate"))
    raw_change_rate = diff_result.get("change_rate")
    change_rate = _finite_float(raw_change_rate)
    false_negatives = _nonnegative_int(diff_result.get("false_negative"))
    samples_checked = _nonnegative_int(
        diff_result.get("samples_checked", diff_result.get("total"))
    )

    if (
        false_negative_rate is None
        or false_negative_rate < 0.0
        or false_negative_rate > 1.0
        or false_negatives is None
        or samples_checked is None
        or samples_checked == 0
        or false_negatives > samples_checked
        or (raw_change_rate is not None and change_rate is None)
    ):
        return blocked_result

    if false_negative_rate > threshold:
        return CanaryPromotionGateResult(
            allowed=False,
            reason="promotion_blocked_false_negative_rate_exceeded",
            false_negative_rate=false_negative_rate,
            false_negative_threshold=threshold,
            change_rate=change_rate,
            false_negatives=false_negatives,
            samples_checked=samples_checked,
        )

    return CanaryPromotionGateResult(
        allowed=True,
        reason="promotion_allowed",
        false_negative_rate=false_negative_rate,
        false_negative_threshold=threshold,
        change_rate=change_rate,
        false_negatives=false_negatives,
        samples_checked=samples_checked,
    )


def canary_promotion_allowed(
    diff_result: Any,
    *,
    false_negative_threshold: float = DEFAULT_FALSE_NEGATIVE_PROMOTION_THRESHOLD,
) -> bool:
    """Return whether canary replay metrics pass the promotion gate."""
    return evaluate_canary_promotion_gate(
        diff_result,
        false_negative_threshold=false_negative_threshold,
    ).allowed


def canary_bucket(request_id: str, canary_ratio: float) -> str:
    """Assign request to stable/canary bucket deterministically.

    Security note:
        This uses SHA-256 hash bucketing for stable assignment and avoids
        random sources that could create inconsistent cross-node behavior.
    """
    ratio = float(canary_ratio)
    if ratio != ratio:  # NaN guard
        ratio = 0.0
    ratio = max(0.0, min(1.0, ratio))
    digest = hashlib.sha256(str(request_id).encode("utf-8")).digest()
    point = int.from_bytes(digest[:8], "big") / float(2**64)
    return "canary" if point < ratio else "stable"
