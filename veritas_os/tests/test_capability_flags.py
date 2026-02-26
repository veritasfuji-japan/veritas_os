"""Capability flag behavior for optional integrations.

These tests ensure optional imports are controlled by explicit feature flags
rather than implicit import success.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _restore_capability_modules_after_test():
    """Restore env-driven capability modules after each test.

    The capability tests intentionally reload modules with temporary env vars.
    Without resetting module globals after each test, later test files can
    observe stale capability states and fail nondeterministically.
    """
    yield

    import veritas_os.core.config as config_mod

    importlib.reload(config_mod)
    for module_name in (
        "veritas_os.core.kernel",
        "veritas_os.core.fuji",
        "veritas_os.core.memory",
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)


def _reload_config_and(module_name: str):
    """Reload config first, then target module to apply env-driven flags."""
    import veritas_os.core.config as config_mod

    config_mod = importlib.reload(config_mod)
    target_mod = importlib.import_module(module_name)
    target_mod = importlib.reload(target_mod)
    return config_mod, target_mod


def test_kernel_capability_flags_disable_optional_layers(monkeypatch):
    """Kernel optional layers can be disabled by explicit capability flags."""
    monkeypatch.setenv("VERITAS_CAP_KERNEL_REASON", "0")
    monkeypatch.setenv("VERITAS_CAP_KERNEL_STRATEGY", "0")
    monkeypatch.setenv("VERITAS_CAP_KERNEL_SANITIZE", "0")

    _, kernel_mod = _reload_config_and("veritas_os.core.kernel")

    assert kernel_mod.reason_core is None
    assert kernel_mod.strategy_core is None
    assert kernel_mod._HAS_SANITIZE is False


def test_fuji_tool_bridge_flag_blocks_call_tool(monkeypatch):
    """Fuji blocks external tool bridge when capability flag is disabled."""
    monkeypatch.setenv("VERITAS_CAP_FUJI_TOOL_BRIDGE", "0")

    _, fuji_mod = _reload_config_and("veritas_os.core.fuji")

    try:
        fuji_mod.call_tool("web_search", query="veritas")
        assert False, "Expected RuntimeError when tool bridge is disabled"
    except RuntimeError as exc:
        assert "VERITAS_CAP_FUJI_TOOL_BRIDGE" in str(exc)


def test_memory_joblib_flag_disables_loader(monkeypatch):
    """Memory module disables joblib model loading via capability flag."""
    monkeypatch.setenv("VERITAS_CAP_MEMORY_JOBLIB_MODEL", "0")

    _, memory_mod = _reload_config_and("veritas_os.core.memory")

    assert memory_mod.joblib_load is None
