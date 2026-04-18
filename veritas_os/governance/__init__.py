"""Governance domain persistence abstractions."""

from veritas_os.governance.config import get_governance_backend, validate_governance_backend
from veritas_os.governance.factory import create_governance_repository
from veritas_os.governance.file_repository import FileGovernanceRepository
from veritas_os.governance.models import GovernancePolicyEventRecord, GovernancePolicyRecord
from veritas_os.governance.postgresql_repository import PostgresGovernanceRepository
from veritas_os.governance.repository import GovernanceRepository

__all__ = [
    "create_governance_repository",
    "FileGovernanceRepository",
    "get_governance_backend",
    "GovernancePolicyEventRecord",
    "GovernancePolicyRecord",
    "PostgresGovernanceRepository",
    "GovernanceRepository",
    "validate_governance_backend",
]
