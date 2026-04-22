"""Compatibility layer for bind adjudication.

This module re-exports the bind core entrypoint and adapter protocol to avoid
breaking existing imports.
"""

from __future__ import annotations

from veritas_os.policy.bind_core.core import (
    BindBoundaryAdapter,
    BindExecutionCheckResult,
    BindPolicyConfig,
    ReferenceBindAdapter,
    execute_bind_adjudication,
)


def execute_bind_boundary(*args, **kwargs):
    """Backward-compatible alias of ``execute_bind_adjudication``."""
    return execute_bind_adjudication(*args, **kwargs)


__all__ = [
    "BindBoundaryAdapter",
    "BindExecutionCheckResult",
    "BindPolicyConfig",
    "ReferenceBindAdapter",
    "execute_bind_boundary",
    "execute_bind_adjudication",
]
