"""FUJI policy diff replay and canary rollout utilities.

This module provides P0-3 controls described in the code review:
- deterministic A/B replay against old/new policies
- allow/hold/deny transition metrics
- false-positive / false-negative estimates when expected labels exist
- deterministic canary assignment by request id

The implementation is scoped to FUJI policy evaluation only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from typing import Any, Dict, Iterable, List, Mapping, Optional

from veritas_os.core import fuji

_ALLOWED_DECISIONS = {"allow", "hold", "deny"}


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
    """Evaluate one sample through FUJI's policy rule engine."""
    result = fuji._apply_policy(  # pylint: disable=protected-access
        risk=float(sample.risk),
        categories=list(sample.categories),
        stakes=float(sample.stakes),
        telos_score=float(sample.telos_score),
        policy=dict(policy),
    )
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
        if expected is not None:
            labeled += 1
            if after in {"hold", "deny"} and expected == "allow":
                fp += 1
                is_fp = True
            elif after == "allow" and expected in {"hold", "deny"}:
                fn += 1
                is_fn = True

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
    fp_rate = (fp / labeled) if labeled else 0.0
    fn_rate = (fn / labeled) if labeled else 0.0

    return {
        "total": total,
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



def canary_bucket(request_id: str, canary_ratio: float) -> str:
    """Assign request to stable/canary bucket deterministically.

    Security note:
        This uses SHA-256 hash bucketing for stable assignment and avoids
        random sources that could create inconsistent cross-node behavior.
    """
    ratio = max(0.0, min(1.0, float(canary_ratio)))
    digest = hashlib.sha256(str(request_id).encode("utf-8")).digest()
    point = int.from_bytes(digest[:8], "big") / float(2**64)
    return "canary" if point < ratio else "stable"
