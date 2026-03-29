"""Backward-compatible module alias for veritas_os.core.memory.memory_distillation."""

from importlib import import_module as _import_module
import logging as _logging
import sys as _sys

_target = _import_module("veritas_os.core.memory.memory_distillation")
if hasattr(_target, "logger"):
    _target.logger = _logging.getLogger(__name__)
_sys.modules[__name__] = _target
