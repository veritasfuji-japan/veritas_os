"""Backward-compatible module alias for veritas_os.core.memory.memory_store_compat."""

from importlib import import_module as _import_module
import logging as _logging
import sys as _sys

from veritas_os.core._shim_deprecation import warn_legacy_core_shim as _warn_legacy_core_shim

_TARGET_MODULE = "veritas_os.core.memory.memory_store_compat"
_warn_legacy_core_shim(legacy_module=__name__, canonical_module=_TARGET_MODULE)
_target = _import_module(_TARGET_MODULE)
if hasattr(_target, "logger"):
    _target.logger = _logging.getLogger(__name__)
_sys.modules[__name__] = _target
