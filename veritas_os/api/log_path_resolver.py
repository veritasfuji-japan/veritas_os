from __future__ import annotations

from pathlib import Path
from typing import Tuple


def effective_log_paths(
    *,
    log_dir: Path,
    log_json: Path,
    log_jsonl: Path,
    default_log_dir: Path,
    default_log_json: Path,
    default_log_jsonl: Path,
) -> Tuple[Path, Path, Path]:
    """Resolve effective trust-log file paths with backward-compatible patch behavior.

    If tests patch only ``LOG_DIR`` and keep ``LOG_JSON``/``LOG_JSONL`` at their
    defaults, this helper makes JSON/JSONL follow the patched directory.
    Explicitly patched JSON paths are always respected.
    """
    resolved_log_json = log_json
    resolved_log_jsonl = log_jsonl

    if resolved_log_json == default_log_json and log_dir != default_log_dir:
        resolved_log_json = log_dir / "trust_log.json"
    if resolved_log_jsonl == default_log_jsonl and log_dir != default_log_dir:
        resolved_log_jsonl = log_dir / "trust_log.jsonl"

    return log_dir, resolved_log_json, resolved_log_jsonl


def effective_shadow_dir(
    *,
    shadow_dir: Path,
    log_dir: Path,
    default_shadow_dir: Path,
    default_log_dir: Path,
) -> Path:
    """Resolve effective shadow snapshot directory with patch-friendly semantics."""
    if shadow_dir == default_shadow_dir and log_dir != default_log_dir:
        return log_dir / "DASH"
    return shadow_dir
