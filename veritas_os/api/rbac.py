# veritas_os/api/rbac.py
"""Role-Based Access Control (RBAC) definitions for VERITAS API.

Defines roles, permissions, and their mappings. The authorization logic
(resolving keys to roles and enforcing permissions) lives in auth.py.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set


class Role(str, enum.Enum):
    """API consumer roles."""

    admin = "admin"
    operator = "operator"
    auditor = "auditor"


class Permission(str, enum.Enum):
    """Fine-grained API permissions."""

    decide = "decide"
    memory_read = "memory_read"
    memory_write = "memory_write"
    trust_log_read = "trust_log_read"
    governance_read = "governance_read"
    governance_write = "governance_write"
    config_write = "config_write"
    compliance_read = "compliance_read"


ROLE_PERMISSIONS: Dict[Role, FrozenSet[Permission]] = {
    Role.admin: frozenset(Permission),
    Role.operator: frozenset({
        Permission.decide,
        Permission.memory_read,
        Permission.memory_write,
        Permission.trust_log_read,
    }),
    Role.auditor: frozenset({
        Permission.trust_log_read,
        Permission.governance_read,
        Permission.compliance_read,
    }),
}


@dataclass(frozen=True)
class RBACPolicy:
    """Immutable snapshot of role-to-permission mappings."""

    mapping: Dict[Role, FrozenSet[Permission]] = field(
        default_factory=lambda: dict(ROLE_PERMISSIONS)
    )

    def has_permission(self, role: Role, permission: Permission) -> bool:
        """Return True when *role* grants *permission*."""
        return permission in self.mapping.get(role, frozenset())
