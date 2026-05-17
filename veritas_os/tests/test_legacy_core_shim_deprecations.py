import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from veritas_os.core._shim_deprecation import warn_legacy_core_shim

ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = ROOT / "veritas_os" / "core"


def _load_shim_module(module_name: str):
    module_relpath = module_name.replace(".", "/") + ".py"
    module_path = ROOT / module_relpath
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return sys.modules[module_name]


def _assert_shim_warning(
    monkeypatch: pytest.MonkeyPatch,
    legacy_module: str,
    canonical_module: str,
) -> None:
    fake_target = types.ModuleType(canonical_module)

    def _fake_import_module(module_name: str):
        assert module_name == canonical_module
        return fake_target

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)

    with pytest.warns(DeprecationWarning) as warning:
        module = _load_shim_module(legacy_module)

    message = str(warning[0].message)
    assert legacy_module in message
    assert canonical_module in message
    assert "v2.2.0" in message
    assert "2026-08-01" in message
    assert module is fake_target


def test_fuji_helpers_shim_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_shim_warning(
        monkeypatch,
        "veritas_os.core.fuji_helpers",
        "veritas_os.core.fuji.fuji_helpers",
    )


def test_memory_helpers_shim_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_shim_warning(
        monkeypatch,
        "veritas_os.core.memory_helpers",
        "veritas_os.core.memory.memory_helpers",
    )


def test_pipeline_helpers_shim_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_shim_warning(
        monkeypatch,
        "veritas_os.core.pipeline_helpers",
        "veritas_os.core.pipeline.pipeline_helpers",
    )


def test_shim_deprecation_helper_message_contract() -> None:
    with pytest.warns(DeprecationWarning) as warning:
        warn_legacy_core_shim(
            legacy_module="veritas_os.core.old",
            canonical_module="veritas_os.core.new.old",
        )

    message = str(warning[0].message)
    assert "veritas_os.core.old" in message
    assert "veritas_os.core.new.old" in message
    assert "v2.2.0" in message
    assert "2026-08-01" in message


def _is_legacy_shim_source(text: str) -> bool:
    return (
        text.startswith('"""Backward-compatible module alias')
        and "import_module(" in text
        and "veritas_os.core." in text
        and (
            "sys.modules[__name__] = _target" in text
            or "_sys.modules[__name__] = _target" in text
        )
    )


def test_all_legacy_core_shims_call_deprecation_helper() -> None:
    missing: list[str] = []
    for path in sorted(CORE_DIR.glob("*.py")):
        if path.name == "_shim_deprecation.py":
            continue
        text = path.read_text(encoding="utf-8")
        if not _is_legacy_shim_source(text):
            continue
        if "warn_legacy_core_shim" not in text:
            missing.append(path.relative_to(ROOT).as_posix())

    assert not missing, (
        "Legacy core shims missing deprecation warning: " + ", ".join(missing)
    )
