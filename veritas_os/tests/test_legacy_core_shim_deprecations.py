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

    previous_legacy = sys.modules.get(legacy_module)
    had_previous_legacy = legacy_module in sys.modules
    try:
        sys.modules.pop(legacy_module, None)
        with pytest.warns(DeprecationWarning) as warning:
            module = _load_shim_module(legacy_module)

        message = str(warning[0].message)
        assert legacy_module in message
        assert canonical_module in message
        assert "v2.2.0" in message
        assert "2026-08-01" in message
        assert module is fake_target
    finally:
        if had_previous_legacy:
            sys.modules[legacy_module] = previous_legacy
        else:
            sys.modules.pop(legacy_module, None)


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



def test_nested_memory_model_shim_emits_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_shim_warning(
        monkeypatch,
        "veritas_os.core.models.memory_model",
        "veritas_os.core.memory.models",
    )


def test_pipeline_compat_shim_preserves_pipeline_logger_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_target = types.ModuleType("veritas_os.core.pipeline.pipeline_compat")
    fake_target.logger = None

    def _fake_import_module(module_name: str):
        assert module_name == "veritas_os.core.pipeline.pipeline_compat"
        return fake_target

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)

    legacy_module = "veritas_os.core.pipeline_compat"
    previous = sys.modules.get(legacy_module)
    had_previous = legacy_module in sys.modules
    try:
        sys.modules.pop(legacy_module, None)
        with pytest.warns(DeprecationWarning):
            module = _load_shim_module(legacy_module)

        assert module is fake_target
        assert fake_target.logger.name == "veritas_os.core.pipeline"
    finally:
        if had_previous:
            sys.modules[legacy_module] = previous
        else:
            sys.modules.pop(legacy_module, None)


def test_pipeline_web_adapter_shim_preserves_pipeline_logger_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_target = types.ModuleType("veritas_os.core.pipeline.pipeline_web_adapter")
    fake_target.logger = None

    def _fake_import_module(module_name: str):
        assert module_name == "veritas_os.core.pipeline.pipeline_web_adapter"
        return fake_target

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)

    legacy_module = "veritas_os.core.pipeline_web_adapter"
    previous = sys.modules.get(legacy_module)
    had_previous = legacy_module in sys.modules
    try:
        sys.modules.pop(legacy_module, None)
        with pytest.warns(DeprecationWarning):
            module = _load_shim_module(legacy_module)

        assert module is fake_target
        assert fake_target.logger.name == "veritas_os.core.pipeline"
    finally:
        if had_previous:
            sys.modules[legacy_module] = previous
        else:
            sys.modules.pop(legacy_module, None)


def test_assert_shim_warning_restores_legacy_sys_modules_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_module = "veritas_os.core.fuji_helpers"
    sentinel = types.ModuleType(legacy_module)
    previous = sys.modules.get(legacy_module)
    had_previous = legacy_module in sys.modules
    try:
        sys.modules[legacy_module] = sentinel
        _assert_shim_warning(
            monkeypatch,
            legacy_module,
            "veritas_os.core.fuji.fuji_helpers",
        )
        assert sys.modules[legacy_module] is sentinel
    finally:
        if had_previous:
            sys.modules[legacy_module] = previous
        else:
            sys.modules.pop(legacy_module, None)


def test_assert_shim_warning_removes_legacy_sys_modules_entry_when_absent_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_module = "veritas_os.core.fuji_helpers"
    previous = sys.modules.get(legacy_module)
    had_previous = legacy_module in sys.modules
    try:
        sys.modules.pop(legacy_module, None)
        _assert_shim_warning(
            monkeypatch,
            legacy_module,
            "veritas_os.core.fuji.fuji_helpers",
        )
        assert legacy_module not in sys.modules
    finally:
        if had_previous:
            sys.modules[legacy_module] = previous
        else:
            sys.modules.pop(legacy_module, None)


def test_memory_package_prefers_canonical_memory_models_import() -> None:
    memory_init = (CORE_DIR / "memory" / "__init__.py").read_text(encoding="utf-8")

    canonical_import = "from . import models as memory_model_core"
    legacy_import = (
        "from veritas_os.core.models import memory_model "
        "as memory_model_core"
    )

    assert canonical_import in memory_init
    assert legacy_import in memory_init
    assert memory_init.index(canonical_import) < memory_init.index(legacy_import)
    assert "with warnings.catch_warnings():" in memory_init
    assert 'warnings.simplefilter("ignore", DeprecationWarning)' in memory_init


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
    for path in sorted(CORE_DIR.rglob("*.py")):
        if path.name == "_shim_deprecation.py":
            continue
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if not _is_legacy_shim_source(text):
            continue
        if "_warn_legacy_core_shim(" not in text and "warn_legacy_core_shim(" not in text:
            missing.append(path.relative_to(ROOT).as_posix())

    assert not missing, (
        "Legacy core shims missing deprecation warning: " + ", ".join(missing)
    )
