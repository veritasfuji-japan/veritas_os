import pathlib

import yaml

from veritas_os.policy.debate_safety_policy_schema import (
    DebateSafetyPolicy,
    PolicyMode,
)

EXAMPLE_YAML_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs"
    / "debate_safety_policy.example.yaml"
)


def test_example_yaml_parses_against_schema():
    raw = yaml.safe_load(EXAMPLE_YAML_PATH.read_text(encoding="utf-8"))
    policy = DebateSafetyPolicy.model_validate(raw)
    assert policy.mode == PolicyMode.example_only


def test_example_yaml_has_at_least_one_category():
    raw = yaml.safe_load(EXAMPLE_YAML_PATH.read_text(encoding="utf-8"))
    policy = DebateSafetyPolicy.model_validate(raw)
    assert len(policy.categories) >= 1


def test_each_category_has_non_empty_patterns():
    raw = yaml.safe_load(EXAMPLE_YAML_PATH.read_text(encoding="utf-8"))
    policy = DebateSafetyPolicy.model_validate(raw)
    for name, cat in policy.categories.items():
        assert len(cat.patterns) >= 1, f"Category '{name}' has no patterns"
