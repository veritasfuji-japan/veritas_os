# Tests for code review fixes (2026-02)
import numpy as np
import pytest

from veritas_os.core.utils import redact_payload, _truncate
from veritas_os.memory.index_cosine import CosineIndex
from veritas_os.tools.llm_safety import _norm, _heuristic_analyze


# ---- redact_payload: recursion depth limit ----

def test_redact_payload_deep_nesting_does_not_overflow():
    """Deeply nested dicts should not cause RecursionError."""
    data: dict = {}
    current = data
    for i in range(200):
        current["child"] = {}
        current = current["child"]
    current["email"] = "test@example.com"

    result = redact_payload(data)
    assert isinstance(result, dict)


def test_redact_payload_normal_nesting_still_redacts():
    """Normal nesting (< 50 levels) should still redact PII."""
    payload = {"a": {"b": {"email": "user@example.com"}}}
    result = redact_payload(payload)
    assert "user@example.com" not in str(result)


# ---- _truncate: negative max_len guard ----

def test_truncate_negative_max_len():
    """Negative max_len should not raise or produce invalid output."""
    result = _truncate("hello world", max_len=-5)
    assert isinstance(result, str)
    assert result == ""


def test_truncate_zero_max_len():
    """Zero max_len should return empty string."""
    result = _truncate("hello world", max_len=0)
    assert result == ""


def test_truncate_normal_behaviour():
    """Normal truncation should still work."""
    assert _truncate("hello", max_len=100) == "hello"
    assert _truncate("hello world", max_len=8) == "hello..."


# ---- CosineIndex: similarity clipping ----

def test_cosine_search_scores_clipped():
    """Similarity scores should be in [-1.0, 1.0] range."""
    idx = CosineIndex(dim=4)
    idx.add(np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32), ["a"])
    results = idx.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), k=1)
    assert len(results) == 1
    for id_, score in results[0]:
        assert -1.0 <= score <= 1.0


# ---- _norm: casefold for Unicode safety ----

def test_norm_uses_casefold():
    """_norm should use casefold() for proper Unicode case folding."""
    # German sharp s: casefold converts ß → ss, lower() does not
    result = _norm("Straße")
    assert "ss" in result  # casefold result

    result_upper = _norm("HELLO")
    assert result_upper == "hello"


def test_heuristic_still_detects_banned_words():
    """After casefold change, banned word detection should still work."""
    result = _heuristic_analyze("I need to kill")
    assert result["risk_score"] >= 0.8
    assert "illicit" in result["categories"]
