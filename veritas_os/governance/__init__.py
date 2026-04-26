"""Governance domain persistence abstractions."""

from veritas_os.governance.authority_evidence import (
    AuthorityEvidence,
    AuthorityEvidenceValidationResult,
    VerificationResult,
    is_expired,
    is_indeterminate,
    is_present,
    is_scope_granting,
    is_valid,
    validate_authority_evidence,
)
from veritas_os.governance.action_contracts import (
    ActionClassContract,
    ActionClassContractValidationError,
    load_action_class_contract,
    validate_action_class_contract,
)
from veritas_os.governance.config import (
    get_governance_backend,
    validate_governance_backend,
)
from veritas_os.governance.factory import create_governance_repository
from veritas_os.governance.file_repository import FileGovernanceRepository
from veritas_os.governance.models import (
    GovernancePolicyEventRecord,
    GovernancePolicyRecord,
)
from veritas_os.governance.postgresql_repository import PostgresGovernanceRepository
from veritas_os.governance.repository import GovernanceRepository

__all__ = [
    "AuthorityEvidence",
    "AuthorityEvidenceValidationResult",
    "VerificationResult",
    "ActionClassContract",
    "ActionClassContractValidationError",
    "create_governance_repository",
    "FileGovernanceRepository",
    "load_action_class_contract",
    "get_governance_backend",
    "GovernancePolicyEventRecord",
    "GovernancePolicyRecord",
    "PostgresGovernanceRepository",
    "GovernanceRepository",
    "validate_action_class_contract",
    "is_expired",
    "is_indeterminate",
    "is_present",
    "is_scope_granting",
    "is_valid",
    "validate_authority_evidence",
    "validate_governance_backend",
]
