"""Regression tests for robust formatting in ``chainlit_app``."""

from __future__ import annotations

import importlib
import sys
import types


def _load_chainlit_app_module():
    """Load ``chainlit_app`` with a lightweight chainlit stub for tests."""
    chainlit_stub = types.ModuleType("chainlit")

    def _identity_decorator(_func=None):
        def decorator(func):
            return func

        if _func is None:
            return decorator
        return decorator(_func)

    class _Message:
        def __init__(self, content: str):
            self.content = content

        async def send(self):
            return None

        async def update(self):
            return None

    chainlit_stub.on_chat_start = _identity_decorator
    chainlit_stub.on_message = _identity_decorator
    chainlit_stub.Message = _Message

    sys.modules.setdefault("chainlit", chainlit_stub)
    return importlib.import_module("chainlit_app")


module = _load_chainlit_app_module()


def test_format_metrics_ignores_non_numeric_values() -> None:
    """Formatter should skip non-numeric metrics instead of raising an error."""
    result = module.format_metrics(
        {
            "extras": {
                "metrics": {
                    "latency_ms": "oops",
                    "mem_evidence_count": "NaN",
                    "avg_world_utility": "bad",
                }
            }
        }
    )

    assert "メトリクス情報はまだありません" in result


def test_format_memory_and_evidence_handles_bad_confidence() -> None:
    """Formatter should tolerate non-float confidence fields in evidence payloads."""
    result = module.format_memory_and_evidence(
        {
            "evidence": [
                {
                    "source": "memory_store",
                    "snippet": "important memory",
                    "confidence": "unknown",
                }
            ]
        }
    )

    assert "conf=0.00" in result


def test_format_main_answer_handles_string_ema() -> None:
    """Formatter should render EMA when it is delivered as a numeric string."""
    result = module.format_main_answer(
        {
            "chosen": {"title": "A"},
            "gate": {"decision_status": "allow", "risk": 0.1},
            "values": {"total": "1.5", "ema": "2.25"},
        }
    )

    assert "total=1.500 / ema=2.250" in result


def test_format_main_answer_handles_non_numeric_gate_values() -> None:
    """Formatter should default invalid risk/telos values to 0.000."""
    result = module.format_main_answer(
        {
            "chosen": {"title": "A"},
            "gate": {"decision_status": "allow", "risk": "high"},
            "telos_score": "unknown",
            "values": {"total": 1.0},
        }
    )

    assert "FUJIリスク: **0.000**" in result
    assert "Telosスコア: **0.000**" in result


def test_format_web_results_handles_non_dict_tools_payload() -> None:
    """Formatter should avoid crashes for malformed tool payload types."""
    result = module.format_web_results(
        {
            "extras": {
                "env_tools": {
                    "web_search": "broken",
                }
            }
        }
    )

    assert "検索エラー" in result


def test_format_main_answer_ignores_non_dict_plan_steps() -> None:
    """Formatter should skip invalid step items and keep valid planner steps."""
    result = module.format_main_answer(
        {
            "chosen": {"title": "A"},
            "gate": {"decision_status": "allow", "risk": 0.1},
            "values": {"total": 1.0},
            "planner": {
                "steps": ["bad-step", {"title": "valid", "detail": "ok"}],
            },
        }
    )

    assert "bad-step" not in result
    assert "valid" in result
