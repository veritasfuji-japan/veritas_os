import importlib
import importlib.util
import sys
import types
import warnings
from pathlib import Path

import pytest

from veritas_os.core._shim_deprecation import (
    SHIM_REMOVAL_DATE,
    SHIM_REMOVAL_VERSION,
    warn_legacy_core_shim,
)

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

        messages = [str(item.message) for item in warning]
        matching_messages = [
            message
            for message in messages
            if legacy_module in message
            and canonical_module in message
            and SHIM_REMOVAL_VERSION in message
            and SHIM_REMOVAL_DATE in message
        ]
        assert matching_messages, (
            "Expected shim deprecation warning not found. "
            f"legacy_module={legacy_module!r}, "
            f"canonical_module={canonical_module!r}, "
            f"captured_messages={messages!r}"
        )
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
    assert SHIM_REMOVAL_VERSION in message
    assert SHIM_REMOVAL_DATE in message



def _capture_stacklevel_warning(stacklevel: int) -> warnings.WarningMessage:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        warn_legacy_core_shim(
            legacy_module="veritas_os.core.old",
            canonical_module="veritas_os.core.new.old",
            stacklevel=stacklevel,
        )

    assert caught
    return caught[0]


def test_warn_legacy_core_shim_stacklevel_changes_warning_location() -> None:
    level_1 = _capture_stacklevel_warning(1)
    level_2 = _capture_stacklevel_warning(2)

    assert str(level_1.message) == str(level_2.message)
    assert (level_1.filename, level_1.lineno) != (level_2.filename, level_2.lineno)


def test_memory_package_import_does_not_emit_legacy_memory_model_warning() -> None:
    previous_memory = sys.modules.get("veritas_os.core.memory")
    previous_legacy = sys.modules.get("veritas_os.core.models.memory_model")
    previous_llm_client = sys.modules.get("veritas_os.core.llm_client")
    had_memory = "veritas_os.core.memory" in sys.modules
    had_legacy = "veritas_os.core.models.memory_model" in sys.modules
    had_llm_client = "veritas_os.core.llm_client" in sys.modules

    try:
        sys.modules.pop("veritas_os.core.memory", None)
        sys.modules.pop("veritas_os.core.models.memory_model", None)
        sys.modules["veritas_os.core.llm_client"] = types.ModuleType(
            "veritas_os.core.llm_client"
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            importlib.import_module("veritas_os.core.memory")

        messages = [str(item.message) for item in caught]
        assert not any(
            "veritas_os.core.models.memory_model is a deprecated compatibility shim"
            in message
            for message in messages
        )
    finally:
        if had_memory:
            sys.modules["veritas_os.core.memory"] = previous_memory
        else:
            sys.modules.pop("veritas_os.core.memory", None)

        if had_legacy:
            sys.modules["veritas_os.core.models.memory_model"] = previous_legacy
        else:
            sys.modules.pop("veritas_os.core.models.memory_model", None)

        if had_llm_client:
            sys.modules["veritas_os.core.llm_client"] = previous_llm_client
        else:
            sys.modules.pop("veritas_os.core.llm_client", None)


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
        is_legacy_shim = _is_legacy_shim_source(text)
        calls_helper = (
            "_warn_legacy_core_shim(" in text
            or "warn_legacy_core_shim(" in text
        )
        if not is_legacy_shim or calls_helper:
            continue
        missing.append(path.relative_to(ROOT).as_posix())

    assert not missing, (
        "Legacy core shims missing deprecation warning: " + ", ".join(missing)
    )
