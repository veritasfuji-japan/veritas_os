"""Replay utilities for deterministic decision re-execution.

The package re-exports ``ReplayResult`` and ``run_replay`` lazily so helper
imports (for example ``veritas_os.replay.replay_engine._safe_filename_id``)
do not require all replay-time API dependencies during module collection.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["ReplayResult", "run_replay"]


def __getattr__(name: str) -> Any:
    """Resolve replay exports lazily to avoid eager dependency loading."""
    if name in __all__:
        module = importlib.import_module("veritas_os.replay.replay_engine")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
