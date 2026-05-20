"""Validation tests for the Debate safety policy example YAML skeleton."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_debate_safety_policy_example_yaml_parses_and_has_expected_shape() -> None:
    """Example policy file should parse and preserve required scaffold keys."""
    policy_path = Path("configs/debate_safety_policy.example.yaml")

    assert policy_path.exists()
    loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8"))

    assert isinstance(loaded, dict)
    assert loaded.get("schema_version") == 1
    assert isinstance(loaded.get("policy_id"), str)
    assert loaded.get("mode") == "example_only"

    categories = loaded.get("categories")
    assert isinstance(categories, dict)
    assert categories

    for category_name, category in categories.items():
        assert isinstance(category_name, str)
        assert isinstance(category, dict)
        assert isinstance(category.get("severity"), str)
        assert isinstance(category.get("action"), str)
        patterns = category.get("patterns")
        assert isinstance(patterns, list)
        assert patterns
        assert all(isinstance(pattern, str) for pattern in patterns)
