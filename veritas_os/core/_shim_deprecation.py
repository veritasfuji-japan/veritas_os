"""Deprecation helpers for legacy core compatibility shims."""

from __future__ import annotations

import warnings

SHIM_REMOVAL_VERSION = "v2.2.0"
SHIM_REMOVAL_DATE = "2026-08-01"


def warn_legacy_core_shim(
    *,
    legacy_module: str,
    canonical_module: str,
    stacklevel: int = 3,
) -> None:
    """Warn when a legacy core shim import path is used.

    This intentionally uses DeprecationWarning rather than
    FutureWarning/UserWarning so production runtime imports are not noisy by
    default. CI, tests, and application boundaries can opt in with warning
    filters when migration enforcement is desired.
    """
    warnings.warn(
        (
            f"{legacy_module} is a deprecated compatibility shim; "
            f"import {canonical_module} instead. "
            f"Removal planned for VERITAS OS {SHIM_REMOVAL_VERSION}, "
            f"no earlier than {SHIM_REMOVAL_DATE}."
        ),
        DeprecationWarning,
        stacklevel=stacklevel,
    )
