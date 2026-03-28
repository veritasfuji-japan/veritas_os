"""Stable JSON emit utilities for compiled policy artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def stable_json_dumps(payload: Any) -> str:
    """Serialize payload with deterministic formatting for reproducible output."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"


def write_stable_json(path: Path, payload: Any) -> None:
    """Write JSON in a deterministic layout and create parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json_dumps(payload), encoding="utf-8")
