"""Declarative AER-03 evidence-only consumer identity.

This module intentionally contains no observable-digest resolver import or call.
It freezes the identity of the only contemplated evidence-only consumer for the
AER-03 proof round. Runtime wiring is a later material change and reopens AER-02.
"""

from __future__ import annotations

import hashlib
from typing import Final

CALLER_COMPONENT: Final = "ObservableDigestEvidenceConsumerV1"
CALLER_IDENTITY: Final = (
    "veritas_os.audit.observable_digest_evidence_consumer:"
    + CALLER_COMPONENT
)
CALLER_ID_HASH: Final = "sha256:" + hashlib.sha256(
    CALLER_IDENTITY.encode("utf-8")
).hexdigest()
TARGET_ID: Final = "RESOLVER_EVIDENCE_ONLY_ACTIVATION_V1"
RESOLVER_PROFILE: Final = "separate_store_readonly_v1"
NAMESPACE_SCOPE: Final = "wat_observables"
LOCATOR_PREFIX: Final = "separate_store://wat_observables/"
ACTIVATION_CONFIGURATION_ID: Final = "observable_digest_evidence_only_activation_v1"
DEFAULT_ENABLED: Final = False
RESULT_ROLE: Final = "EVIDENCE_ONLY"


class ObservableDigestEvidenceConsumerV1:
    """Identity-only boundary marker; no resolver behavior is wired here."""

    caller_identity: Final = CALLER_IDENTITY
    caller_id_hash: Final = CALLER_ID_HASH
    target_id: Final = TARGET_ID
    resolver_profile: Final = RESOLVER_PROFILE
    namespace_scope: Final = NAMESPACE_SCOPE
    locator_prefix: Final = LOCATOR_PREFIX
    activation_configuration_id: Final = ACTIVATION_CONFIGURATION_ID
    default_enabled: Final = DEFAULT_ENABLED
    result_role: Final = RESULT_ROLE
