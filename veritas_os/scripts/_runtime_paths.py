"""Canonical runtime path resolution for VERITAS scripts.

All scripts in ``veritas_os/scripts/`` MUST use these paths instead of
computing their own.  The runtime tree lives under::

    {project_root}/runtime/{namespace}/
        logs/          # trust_log.jsonl, decide_*.json, meta_log.jsonl
        logs/doctor/   # doctor_report.json, doctor_auto.log/err
        data/          # memory.json, world_state.json, value_stats.json
        datasets/      # training datasets
        benchmarks/    # benchmark result JSONs
        reports/       # generated HTML / JSON reports
        models/        # trained model artifacts

Environment variable overrides (highest priority):
    VERITAS_RUNTIME_ROOT       – override the runtime root directory
    VERITAS_RUNTIME_NAMESPACE  – override the namespace (dev/test/prod/demo)
    VERITAS_ENV                – alternative to RUNTIME_NAMESPACE

When no overrides are set, the default resolves to
``{git_repo_root}/runtime/dev/``.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root from file location
# ---------------------------------------------------------------------------
# This file:  veritas_os/scripts/_runtime_paths.py
# parents[0] = veritas_os/scripts
# parents[1] = veritas_os   (Python package root)
# parents[2] = repo root    (git checkout root)
_PKG_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _PKG_ROOT.parent


def _resolve_namespace() -> str:
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
    """Resolve the runtime root with optional environment override."""
    env_root = (os.getenv("VERITAS_RUNTIME_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser()
    return _PROJECT_ROOT / "runtime"


# ---------------------------------------------------------------------------
# Canonical path constants
# ---------------------------------------------------------------------------
RUNTIME_ROOT = _resolve_runtime_root()
RUNTIME_NAMESPACE = _resolve_namespace()
RUNTIME_DIR = RUNTIME_ROOT / RUNTIME_NAMESPACE

# Logs
LOG_DIR = RUNTIME_DIR / "logs"
TRUST_LOG_JSONL = LOG_DIR / "trust_log.jsonl"
TRUST_LOG_JSON = LOG_DIR / "trust_log.json"

# Doctor
DOCTOR_DIR = LOG_DIR / "doctor"
DOCTOR_REPORT_JSON = DOCTOR_DIR / "doctor_report.json"
DOCTOR_DASHBOARD_HTML = DOCTOR_DIR / "doctor_dashboard.html"

# Data
DATA_DIR = RUNTIME_DIR / "data"

# Benchmarks
BENCH_LOG_DIR = RUNTIME_DIR / "benchmarks"

# Reports
REPORT_DIR = RUNTIME_DIR / "reports"

# Datasets
DATASET_DIR = RUNTIME_DIR / "datasets"

# Models
MODELS_DIR = RUNTIME_DIR / "models"

# DASH / shadow
DASH_DIR = LOG_DIR / "DASH"


def ensure_dirs() -> None:
    """Create canonical runtime directories.

    Scripts should call this before writing files.  Import-time ``mkdir``
    calls are not allowed—use this function explicitly instead.
    """
    for d in (
        LOG_DIR, DOCTOR_DIR, DATA_DIR,
        BENCH_LOG_DIR, REPORT_DIR, DATASET_DIR,
        DASH_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
