"""Tests for Debate safety policy shadow loader and parity report."""

from __future__ import annotations

from pathlib import Path

import pytest

from veritas_os.policy.debate_safety_policy_loader import (
    DebateSafetyPolicySchemaError,
    DebateSafetyPolicyYamlSyntaxError,
    compare_policy_to_hardcoded_inventory,
    load_debate_safety_policy_from_yaml,
)
from veritas_os.policy.debate_safety_policy_schema import PolicyMode


EXAMPLE_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "debate_safety_policy.example.yaml"
)


def test_loader_loads_valid_example_yaml() -> None:
    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)
    assert policy.mode == PolicyMode.example_only
    assert len(policy.categories) >= 1


def test_loader_fails_on_invalid_yaml_syntax(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad_syntax.yaml"
    bad_yaml.write_text("categories: [\n", encoding="utf-8")

    with pytest.raises(DebateSafetyPolicyYamlSyntaxError):
        load_debate_safety_policy_from_yaml(bad_yaml)


def test_loader_fails_on_schema_invalid_yaml(tmp_path: Path) -> None:
    schema_invalid = tmp_path / "schema_invalid.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid",
                "mode: example_only",
                "categories:",
                "  dangerous_terms_ja:",
                "    severity: high",
                "    action: block",
                "    patterns: []",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_fails_on_schema_invalid_empty_pattern_string(tmp_path: Path) -> None:
    schema_invalid = tmp_path / "schema_invalid_empty_pattern.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid-empty-pattern",
                "mode: example_only",
                "categories:",
                "  dangerous_terms_ja:",
                "    severity: high",
                "    action: block",
                "    patterns:",
                '      - ""',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_fails_on_schema_invalid_empty_patterns_list(tmp_path: Path) -> None:
    """patterns: [] must be rejected — list itself must be non-empty (Field min_length=1)."""
    schema_invalid = tmp_path / "schema_invalid_empty_patterns_list.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid-empty-patterns-list",
                "mode: example_only",
                "categories:",
                "  dangerous_terms_ja:",
                "    severity: high",
                "    action: block",
                "    patterns: []",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_fails_on_schema_invalid_empty_categories(tmp_path: Path) -> None:
    schema_invalid = tmp_path / "schema_invalid_empty_categories.yaml"
    schema_invalid.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "policy_id: invalid-empty-categories",
                "mode: example_only",
                "categories: {}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DebateSafetyPolicySchemaError):
        load_debate_safety_policy_from_yaml(schema_invalid)


def test_loader_does_not_call_runtime_enforcement(monkeypatch) -> None:
    called = {"run_debate": False}

    def _fail_run_debate(*args, **kwargs):
        called["run_debate"] = True
        raise AssertionError("run_debate must not be called by shadow loader")

    monkeypatch.setattr("veritas_os.core.debate.run_debate", _fail_run_debate)

    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)

    assert policy.policy_id
    assert called["run_debate"] is False


def test_parity_report_is_conservative_phase2() -> None:
    policy = load_debate_safety_policy_from_yaml(EXAMPLE_YAML_PATH)
    report = compare_policy_to_hardcoded_inventory(policy)

    assert report.status in {"shadow_only", "parity_unknown", "partial_parity"}
    assert report.status == "parity_unknown"
    assert len(report.missing_hardcoded_categories) >= 1
    assert report.hardcoded_pattern_count is not None
    assert report.yaml_pattern_count >= 1
