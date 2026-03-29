"""Backward-compatible module alias for veritas_os.core.pipeline.pipeline_web_adapter."""

from importlib import import_module as _import_module
import logging as _logging
import sys as _sys

_target = _import_module("veritas_os.core.pipeline.pipeline_web_adapter")
if hasattr(_target, "logger"):
    _target.logger = _logging.getLogger("veritas_os.core.pipeline")
_sys.modules[__name__] = _target
