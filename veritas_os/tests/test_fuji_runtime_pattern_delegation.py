"""Regression tests for FUJI runtime prompt-injection pattern delegation."""

from __future__ import annotations

from veritas_os.core import fuji
from veritas_os.core import fuji_injection


def test_runtime_pattern_update_affects_fuji_detection() -> None:
    """Custom policy patterns should be applied to fuji._detect_prompt_injection."""
    original_patterns = fuji_injection._PROMPT_INJECTION_PATTERNS
    policy = {
        "prompt_injection": {
            "patterns": [
                {
                    "pattern": r"super_custom_attack",
                    "weight": 0.7,
                    "label": "custom_attack",
                }
            ]
        }
    }

    try:
        fuji._build_runtime_patterns_from_policy(policy)

        result = fuji._detect_prompt_injection("super_custom_attack")
        assert "custom_attack" in result["signals"]
        assert result["score"] > 0.0
    finally:
        fuji_injection._PROMPT_INJECTION_PATTERNS = original_patterns


def test_runtime_confusable_map_update_affects_fuji_normalize() -> None:
    """Unicode confusable map updates should flow into FUJI normalization."""
    original_confusable_map = fuji_injection._CONFUSABLE_ASCII_MAP
    policy = {"unicode_normalization": {"confusables": {"ℋ": "h"}}}

    try:
        fuji._build_runtime_patterns_from_policy(policy)

        assert fuji._normalize_injection_text("ℋello") == "hello"
    finally:
        fuji_injection._CONFUSABLE_ASCII_MAP = original_confusable_map
