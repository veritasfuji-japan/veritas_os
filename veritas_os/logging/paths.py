# veritas_os/logging/paths.py
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

# リポジトリルート: .../<repo>/veritas_os
REPO_ROOT = Path(__file__).resolve().parents[1]

# scripts ディレクトリ
SCRIPTS_DIR = REPO_ROOT / "scripts"
PROJECT_ROOT = REPO_ROOT.parent

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


def _resolve_log_root() -> Path:
    """Resolve the base log root with optional encrypted-path enforcement."""
    encrypted_root = os.getenv("VERITAS_ENCRYPTED_LOG_ROOT")
    data_base = os.getenv("VERITAS_DATA_DIR")
    log_root_env = os.getenv("VERITAS_LOG_ROOT")
    require_encrypted = _as_bool_env(
        os.getenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR")
    )

    if encrypted_root:
        log_root = Path(encrypted_root).expanduser()
    elif data_base:
        log_root = Path(data_base).expanduser() / "logs"
    elif log_root_env:
        log_root = Path(log_root_env).expanduser()
    else:
        runtime_namespace = _resolve_runtime_namespace()
        runtime_root = _resolve_runtime_root()
        log_root = runtime_root / runtime_namespace / "logs"

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


def _resolve_runtime_namespace() -> str:
    """Return runtime namespace for data separation (dev/test/demo/prod)."""
    explicit = (os.getenv("VERITAS_RUNTIME_NAMESPACE") or "").strip().lower()
    if explicit:
        return explicit

    env_profile = (os.getenv("VERITAS_ENV") or "").strip().lower()
    mapping = {
        "production": "prod",
        "prod": "prod",
        "staging": "dev",
        "stage": "dev",
        "development": "dev",
        "dev": "dev",
        "test": "test",
        "testing": "test",
        "demo": "demo",
    }
    return mapping.get(env_profile, "dev")


def _resolve_runtime_root() -> Path:
    """Resolve repository runtime root with optional environment override."""
    env_root = (os.getenv("VERITAS_RUNTIME_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser()
    return PROJECT_ROOT / "runtime"


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


# ★ 追加: VERITAS_DATA_DIR があればそちらを最優先で使う
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
RUNTIME_NAMESPACE = _resolve_runtime_namespace()
RUNTIME_ROOT = _resolve_runtime_root()
RUNTIME_DIR = RUNTIME_ROOT / RUNTIME_NAMESPACE
DATA_DIR = RUNTIME_DIR / "data"

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
    "RUNTIME_NAMESPACE",
    "RUNTIME_ROOT",
    "RUNTIME_DIR",
    "DATA_DIR",
    "VAL_JSON",
    "META_LOG",
    "ensure_runtime_dirs",
]
