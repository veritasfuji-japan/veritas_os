"""Backward-compatible module alias for veritas_os.core.fuji.fuji_policy_rollout."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("veritas_os.core.fuji.fuji_policy_rollout")
