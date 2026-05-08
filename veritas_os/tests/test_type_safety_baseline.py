from __future__ import annotations

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT_PATH = REPO_ROOT / "scripts" / "quality" / "check_type_baseline.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _load_check_script_module():
    spec = importlib.util.spec_from_file_location(
        "check_type_baseline", CHECK_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load check_type_baseline module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_script_exists() -> None:
    assert CHECK_SCRIPT_PATH.exists()


def test_baseline_targets_are_defined_and_non_empty() -> None:
    module = _load_check_script_module()
    targets = module.BASELINE_TARGETS
    assert isinstance(targets, list)
    assert targets
    assert "scripts/demo/one_day_poc_shared.py" in targets


def test_baseline_targets_exist() -> None:
    module = _load_check_script_module()
    for target in module.BASELINE_TARGETS:
        assert (REPO_ROOT / target).exists()


def test_pyproject_has_mypy_in_dev_dependencies() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]
    assert "mypy==1.13.0" in dev_dependencies


def test_pyproject_has_mypy_tool_config() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert "mypy" in pyproject["tool"]


def test_check_script_does_not_use_shell_true() -> None:
    source = CHECK_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_type_baseline_passes_when_mypy_available() -> None:
    if importlib.util.find_spec("mypy") is None:
        pytest.skip("mypy is not installed")

    result = subprocess.run(
        [sys.executable, "-m", "scripts.quality.check_type_baseline"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_script_has_python_shebang() -> None:
    source = CHECK_SCRIPT_PATH.read_text(encoding="utf-8")
    assert source.startswith("#!/usr/bin/env python3")
