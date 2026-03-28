# veritas_os/logging/paths.py
from __future__ import annotations

import logging
import os
import stat
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]

# scripts ディレクトリ
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ---- ログ周り ----


def _as_bool_env(value: str | None) -> bool:
    """Return True when the environment value represents an enabled flag."""
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _validate_resolved_path(path: Path) -> Path:
    """Validate that a resolved path does not traverse into sensitive system dirs."""
    # Reject paths containing '..' components before resolution
    if ".." in path.parts:
        raise RuntimeError(
            "Path traversal detected: path contains '..' components"
        )
    resolved = path.resolve()
    resolved_str = str(resolved)
    # Also check resolved path for '..' (symlink traversal)
    if ".." in resolved.parts:
        raise RuntimeError(
            "Path traversal detected: resolved path contains '..' components"
        )
    # Block sensitive system directories
    _sensitive = ("/etc", "/var/run", "/proc", "/sys", "/dev", "/boot")
    for sp in _sensitive:
        if resolved_str == sp or resolved_str.startswith(sp + "/"):
            raise RuntimeError(
                f"Log path must not be within sensitive system directory: {sp}"
            )
    return resolved


def _resolve_runtime_env() -> str:
    """Return normalized runtime namespace.

    Supported namespaces: ``dev``, ``test``, ``demo``, ``prod``.
    Any unsupported value falls back to ``dev``.
    """
    env = (os.getenv("VERITAS_RUNTIME_ENV") or "dev").strip().lower()
    if env not in {"dev", "test", "demo", "prod"}:
        logger.warning(
            "Unsupported VERITAS_RUNTIME_ENV=%r; falling back to 'dev'.",
            env,
        )
        return "dev"
    return env


def _resolve_runtime_root() -> Path:
    """Resolve base runtime root directory with environment separation."""
    explicit = os.getenv("VERITAS_RUNTIME_ROOT")
    if explicit:
        root = Path(explicit).expanduser()
    elif _resolve_runtime_env() == "test":
        root = Path(tempfile.gettempdir()) / "veritas_os" / "runtime" / "test"
    else:
        root = REPO_ROOT / "runtime" / _resolve_runtime_env()
    return _validate_resolved_path(root)


def _resolve_log_root() -> Path:
    """Resolve the base log root with optional encrypted-path enforcement."""
    encrypted_root = os.getenv("VERITAS_ENCRYPTED_LOG_ROOT")
    log_root_env = os.getenv("VERITAS_LOG_ROOT")
    require_encrypted = _as_bool_env(
        os.getenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR")
    )

    if encrypted_root:
        log_root = Path(encrypted_root).expanduser()
    elif log_root_env:
        log_root = Path(log_root_env).expanduser()
    else:
        log_root = _resolve_runtime_root() / "logs"

    # ★ セキュリティ修正: パストラバーサル・機密ディレクトリへの書き込みを防止
    _validate_resolved_path(log_root)

    if require_encrypted:
        if not encrypted_root:
            raise RuntimeError(
                "VERITAS_REQUIRE_ENCRYPTED_LOG_DIR=1 requires "
                "VERITAS_ENCRYPTED_LOG_ROOT to be set."
            )
        encrypted_path = Path(encrypted_root).expanduser().resolve()
        try:
            log_root.resolve().relative_to(encrypted_path)
        except ValueError as exc:
            raise RuntimeError(
                "LOG_ROOT must be within VERITAS_ENCRYPTED_LOG_ROOT when "
                "VERITAS_REQUIRE_ENCRYPTED_LOG_DIR=1."
            ) from exc

    return log_root


def _ensure_secure_permissions(path: Path) -> None:
    """Restrict permissions to owner-only (700) for log directories."""
    if os.name == "nt":
        return
    try:
        current_mode = stat.S_IMODE(path.stat().st_mode)
        if current_mode != 0o700:
            os.chmod(path, 0o700)
    except OSError as exc:
        logger.warning("Failed to set permissions on %s: %s", path, exc)


LOG_ROOT = _resolve_log_root()

# trust_log など通常ログ
LOG_DIR = LOG_ROOT
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# decide_* や shadow 用
DASH_DIR = LOG_ROOT / "DASH"

# doctor/shadow decide 用ディレクトリ
SHADOW_DIR = DASH_DIR

# 学習用データセット
DATASET_DIR = DASH_DIR

# ---- ValueCore 用データ ----

# Runtime-separated state/data path
PROJECT_ROOT = REPO_ROOT.parent
DATA_DIR = _resolve_runtime_root() / "state"

# ValueCore のEMA等
VAL_JSON = DATA_DIR / "value_stats.json"

# ReasonOS メタログ
META_LOG = LOG_DIR / "meta_log.jsonl"


def ensure_runtime_dirs() -> None:
    """Create and harden runtime directories for logging paths.

    This function is intentionally explicit so importing ``veritas_os.logging.paths``
    does not mutate the filesystem (M-2 import-time side effect reduction).
    """
    for directory in (LOG_ROOT, DASH_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        _ensure_secure_permissions(directory)

__all__ = [
    "REPO_ROOT",
    "SCRIPTS_DIR",
    "LOG_ROOT",
    "LOG_DIR",
    "LOG_JSON",
    "LOG_JSONL",
    "DASH_DIR",
    "SHADOW_DIR",
    "DATASET_DIR",
    "PROJECT_ROOT",
    "DATA_DIR",
    "VAL_JSON",
    "META_LOG",
    "ensure_runtime_dirs",
]
