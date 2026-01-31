# veritas_os/tests/test_fuji_codes.py
"""Tests for FUJI Standard Codes and rejection responses."""
from __future__ import annotations

import pytest

from veritas_os.core.fuji_codes import build_fuji_rejection, validate_fuji_code


def test_validate_fuji_code_accepts_known():
    """Registered FUJI codes should pass validation."""
    validate_fuji_code("F-2101")


@pytest.mark.parametrize("code", ["F-999", "F-5000", "X-1002", "F-1999"])
def test_validate_fuji_code_rejects_invalid(code):
    """Invalid or unknown FUJI codes should raise."""
    with pytest.raises(ValueError):
        validate_fuji_code(code)


def test_build_fuji_rejection_structure():
    """Rejected payload should match the standard JSON structure."""
    payload = build_fuji_rejection("F-2101", trust_log_id="TL-20250101-0001")
    assert payload["status"] == "REJECTED"
    assert payload["gate"] == "FUJI_SAFETY_GATE_v2"
    assert payload["error"]["code"] == "F-2101"
    assert payload["error"]["layer"] == "Logic & Debate"
    assert payload["feedback"]["action"] == "RE-DEBATE"
    assert payload["trust_log_id"] == "TL-20250101-0001"


@pytest.mark.parametrize(
    ("code", "layer"),
    [
        ("F-1002", "Data & Evidence"),
        ("F-2101", "Logic & Debate"),
        ("F-3001", "Value & Policy"),
        ("F-4003", "Safety & Security"),
    ],
)
def test_build_fuji_rejection_layers(code, layer):
    """Each layer should return the correct layer label."""
    payload = build_fuji_rejection(code, trust_log_id="TL-20250101-0002")
    assert payload["error"]["layer"] == layer


def test_f_2101_action_is_redebate():
    """F-2101 must always use RE-DEBATE action."""
    payload = build_fuji_rejection("F-2101", trust_log_id="TL-20250101-0003")
    assert payload["feedback"]["action"] == "RE-DEBATE"


def test_f_4003_is_blocking_medium_or_higher():
    """F-4003 should be blocking and at least MEDIUM severity."""
    payload = build_fuji_rejection("F-4003", trust_log_id="TL-20250101-0004")
    assert payload["error"]["blocking"] is True
    assert payload["error"]["severity"] in {"MEDIUM", "HIGH"}
