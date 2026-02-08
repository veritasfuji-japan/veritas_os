# veritas_os/core/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
VERITAS core package exports.

IMPORTANT (ISSUE-4):
- optional / fragile modules (e.g. experiments) must NOT crash package import.
- keep this __init__ lightweight: avoid importing heavy modules at import time.
- NEVER hard-fail import due to optional modules.
- Provide stable names via lazy imports (PEP 562: __getattr__).
"""

from typing import Optional, Any, Dict
import importlib

# ============================================================
# Lazy exports (stable modules)  ※ISSUE-4の本命: core importを軽くする
# ============================================================

_LAZY_EXPORTS: Dict[str, str] = {
    # stable public names -> relative module path
    "veritas_core": ".kernel",
    "fuji_core": ".fuji",
    "mem": ".memory",
    "value_core": ".value_core",
    "world_model": ".world",
    "planner_core": ".planner",
    "llm_client": ".llm_client",
    "reason_core": ".reason",
    "debate_core": ".debate",
}

# cache for loaded modules/objects
_CACHE: Dict[str, Any] = {}

__all__ = [
    *list(_LAZY_EXPORTS.keys()),
    # optional
    "experiments",
    "EXPERIMENTS_OK",
    "EXPERIMENTS_IMPORT_ERROR",
    "EXPERIMENTS_ATTEMPTED",
    "try_import_experiments",
]

def __getattr__(name: str) -> Any:
    """
    Lazy attribute loader:
    - from veritas_os.core import mem, value_core ... を壊さず
    - import時に重い依存を評価しない（ISSUE-4対策）
    """
    if name in _CACHE:
        return _CACHE[name]

    mod_path = _LAZY_EXPORTS.get(name)
    if not mod_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    mod = importlib.import_module(mod_path, __name__)
    _CACHE[name] = mod
    return mod


# ============================================================
# OPTIONAL: experiments (import isolation)
# ============================================================

experiments: Optional[Any] = None
EXPERIMENTS_OK: bool = False
EXPERIMENTS_IMPORT_ERROR: str | None = None
EXPERIMENTS_ATTEMPTED: bool = False


def try_import_experiments(force: bool = False) -> Optional[Any]:
    """
    Lazy import accessor for experiments.

    - success: EXPERIMENTS_OK=True and returns module
    - fail:    EXPERIMENTS_OK=False and returns None (and sets error)
    - force:   clear cached failure and retry import

    NOTE:
    - Always uses relative import (".experiments", __name__) to be robust in tests/renames.
    - Never raises; it only records the error and returns None.
    """
    global experiments, EXPERIMENTS_OK, EXPERIMENTS_IMPORT_ERROR, EXPERIMENTS_ATTEMPTED

    if force:
        experiments = None
        EXPERIMENTS_OK = False
        EXPERIMENTS_IMPORT_ERROR = None
        EXPERIMENTS_ATTEMPTED = False

    # already loaded
    if experiments is not None and EXPERIMENTS_OK:
        return experiments

    # already failed once (don't retry in hot paths)
    if experiments is None and EXPERIMENTS_IMPORT_ERROR is not None:
        return None

    EXPERIMENTS_ATTEMPTED = True

    try:
        mod = importlib.import_module(".experiments", __name__)
        experiments = mod
        EXPERIMENTS_OK = True
        EXPERIMENTS_IMPORT_ERROR = None
        return experiments
    except Exception as e:
        experiments = None
        EXPERIMENTS_OK = False
        EXPERIMENTS_IMPORT_ERROR = f"{type(e).__name__}: {e}"
        return None



