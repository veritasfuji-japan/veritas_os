"""Factory for governance repositories."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from veritas_os.governance.config import validate_governance_backend
from veritas_os.governance.file_repository import FileGovernanceRepository
from veritas_os.governance.postgresql_repository import PostgresGovernanceRepository
from veritas_os.governance.repository import GovernanceRepository
from veritas_os.observability.metrics import set_db_backend_selected

logger = logging.getLogger(__name__)


def create_governance_repository(
    *,
    policy_path: Path,
    history_path: Path,
    lock: threading.Lock,
    policy_history_max: int,
    has_atomic_io: bool,
) -> GovernanceRepository:
    """Create governance repository based on ``VERITAS_GOVERNANCE_BACKEND``."""
    backend = validate_governance_backend()
    if backend == "postgresql":
        logger.info("Governance backend: postgresql")
        set_db_backend_selected("governance", "postgresql")
        repository = PostgresGovernanceRepository()
        repository.health_check()
        return repository

    logger.info("Governance backend: file")
    set_db_backend_selected("governance", "file")
    return FileGovernanceRepository(
        policy_path=policy_path,
        history_path=history_path,
        lock=lock,
        policy_history_max=policy_history_max,
        has_atomic_io=has_atomic_io,
    )
