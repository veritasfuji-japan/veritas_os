from __future__ import annotations

import hashlib
import json
from pathlib import Path

from veritas_os.audit import observable_digest_evidence_consumer as consumer

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "security" / "observable_digest_resolver_aer03_named_target_caller_v1.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_aer03_exact_named_target_and_caller_are_frozen() -> None:
    target = _manifest()["target"]
    assert target["target_id"] == consumer.TARGET_ID
    assert target["caller_module"] == "veritas_os.audit.observable_digest_evidence_consumer"
    assert target["caller_component"] == consumer.CALLER_COMPONENT
    assert target["caller_identity"] == consumer.CALLER_IDENTITY
    assert target["resolver_profile"] == consumer.RESOLVER_PROFILE
    assert target["namespace_scope"] == consumer.NAMESPACE_SCOPE
    assert target["activation_configuration_id"] == consumer.ACTIVATION_CONFIGURATION_ID
    assert target["default_enabled"] is False
    assert consumer.DEFAULT_ENABLED is False
    assert target["caller_role"] == consumer.RESULT_ROLE == "EVIDENCE_ONLY"


def test_aer03_caller_hash_has_deterministic_provenance() -> None:
    expected = "sha256:" + hashlib.sha256(
        consumer.CALLER_IDENTITY.encode("utf-8")
    ).hexdigest()
    assert consumer.CALLER_ID_HASH == expected
    assert _manifest()["target"]["caller_id_hash_derivation"] == (
        "sha256(UTF-8 exact caller_identity)"
    )


def test_aer03_named_caller_does_not_wire_resolver() -> None:
    source = (ROOT / "veritas_os/audit/observable_digest_evidence_consumer.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "from veritas_os.audit.observable_digest_resolver import",
        "import veritas_os.audit.observable_digest_resolver",
        "resolve_separate_store_readonly_v1(",
        "SeparateStoreReadonlyProfile(",
    )
    assert not any(token in source for token in forbidden)


def test_aer03_remains_non_authorizing_and_non_effect_bearing() -> None:
    manifest = _manifest()
    assert manifest["status"] == "DEFINED_NOT_AUTHORIZED_NOT_ACTIVATED"
    assert all(value is False for value in manifest["forbidden_semantics"].values())
