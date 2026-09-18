"""Runtime adapter for compiled policy artifacts.

This module bridges compiled policy artifacts (canonical IR / manifest / bundle)
into runtime-evaluable policy structures used by governance and pipeline code.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .hash import semantic_policy_hash
from .ir import CanonicalPolicyIR
from .signing import verify_manifest_ed25519

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimePolicy:
    """Runtime-ready policy object derived from canonical policy IR."""

    policy_id: str
    version: str
    title: str
    description: str
    effective_date: str | None
    scope: Dict[str, List[str]]
    conditions: List[Dict[str, Any]]
    constraints: List[Dict[str, Any]]
    requirements: Dict[str, Any]
    outcome: Dict[str, str]
    obligations: List[str]
    test_vectors: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    source_refs: List[str]


@dataclass(frozen=True)
class ManifestVerificationResult:
    """Verifier-derived manifest trust result.

    signature_verified is true only after successful Ed25519 verification
    with trusted public-key material. A SHA-256 integrity check never sets it.
    """

    integrity_verified: bool
    signature_verified: bool
    algorithm: str
    signer_id: str = ""


@dataclass(frozen=True)
class RuntimePolicyBundle:
    """Runtime policy bundle adapted from compiled artifacts."""

    schema_version: str
    policy_id: str
    version: str
    semantic_hash: str
    compiler_version: str
    compiled_at: str
    runtime_policies: List[RuntimePolicy]
    manifest: Dict[str, Any]
    manifest_integrity_verified: bool = False
    signature_verified: bool = False
    signature_algorithm: str = ""
    signer_id: str = ""
    bundle_contents_verified: bool = False


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"failed to read policy bundle file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in policy bundle file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping json at {path}, got {type(data).__name__}")
    return data


def _active_policy_posture_is_strict() -> bool:
    try:
        from veritas_os.core.posture import get_active_posture

        return bool(get_active_posture().is_strict)
    except (ImportError, AttributeError):
        return False


def _ed25519_required(*, is_strict: bool) -> bool:
    explicit = os.getenv("VERITAS_POLICY_REQUIRE_ED25519", "").strip().lower()
    return is_strict or explicit in {"1", "true", "yes"}


def _parse_json_mapping_bytes(raw: bytes, *, label: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid JSON in {label}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping JSON in {label}")
    return data


def _resolve_verification_public_key(
    public_key_pem: bytes | None,
) -> bytes | None:
    if public_key_pem is not None:
        return public_key_pem

    key_path_str = os.environ.get("VERITAS_POLICY_VERIFY_KEY")
    if not key_path_str:
        return None

    key_path = Path(key_path_str)
    try:
        if key_path.is_file():
            return key_path.read_bytes()
    except OSError as exc:
        logger.warning(
            "failed to read configured policy verification key "
            "(error_type=%s)",
            type(exc).__name__,
        )
    return None


def _verify_manifest_payload(
    *,
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    signature_text: str,
    public_key_pem: bytes | None,
    require_ed25519: bool,
) -> ManifestVerificationResult:
    signing = manifest.get("signing", {})
    if not isinstance(signing, Mapping):
        raise ValueError("manifest signing metadata must be a mapping")

    algorithm = str(signing.get("algorithm", "")).strip().lower()
    if algorithm not in {"ed25519", "sha256"}:
        raise ValueError("unsupported manifest signing algorithm")

    if algorithm == "ed25519":
        pub_key = _resolve_verification_public_key(public_key_pem)
        if pub_key is None:
            raise ValueError(
                "Ed25519 verification requires a trusted public key; "
                "SHA-256 downgrade is not permitted"
            )
        verified = verify_manifest_ed25519(
            manifest_bytes,
            signature_text,
            pub_key,
        )
        return ManifestVerificationResult(
            integrity_verified=verified,
            signature_verified=verified,
            algorithm="ed25519",
            signer_id=(
                str(signing.get("key_id", "")).strip()
                if verified
                else ""
            ),
        )

    if require_ed25519:
        raise ValueError(
            "Ed25519 verification is required; legacy SHA-256 manifest "
            "integrity is insufficient"
        )

    expected = hashlib.sha256(manifest_bytes).hexdigest()
    verified = hmac.compare_digest(expected, signature_text)
    return ManifestVerificationResult(
        integrity_verified=verified,
        signature_verified=False,
        algorithm="sha256",
        signer_id="",
    )


def verify_manifest_signature(
    bundle_dir: str | Path,
    *,
    public_key_pem: bytes | None = None,
) -> bool:
    """Verify manifest.sig without allowing algorithm downgrade.

    An artifact that declares ed25519 is verified only with a trusted Ed25519
    public key. It is never reinterpreted as a SHA-256 artifact when the key is
    missing. Legacy bundles that explicitly declare sha256 are accepted only
    outside strict posture unless Ed25519 is explicitly required.
    """
    root = Path(bundle_dir)
    manifest_path = root / "manifest.json"
    signature_path = root / "manifest.sig"
    if not manifest_path.exists() or not signature_path.exists():
        missing = [
            name
            for name, p in (
                ("manifest.json", manifest_path),
                ("manifest.sig", signature_path),
            )
            if not p.exists()
        ]
        logger.warning(
            "signature verification skipped: missing required artifacts: %s",
            missing,
        )
        return False

    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        logger.warning(
            "failed to read manifest for signature verification "
            "(error_type=%s)",
            type(exc).__name__,
        )
        return False
    try:
        manifest = _parse_json_mapping_bytes(
            manifest_bytes,
            label="manifest.json",
        )
    except ValueError as exc:
        logger.warning(
            "failed to parse manifest.json for signature verification "
            "(error_type=%s)",
            type(exc).__name__,
        )
        return False

    try:
        signature_text = signature_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "failed to read signature file for verification "
            "(error_type=%s)",
            type(exc).__name__,
        )
        return False

    verification = _verify_manifest_payload(
        manifest_bytes=manifest_bytes,
        manifest=manifest,
        signature_text=signature_text,
        public_key_pem=public_key_pem,
        require_ed25519=_ed25519_required(
            is_strict=_active_policy_posture_is_strict()
        ),
    )
    return verification.integrity_verified


def _validate_manifest_bundle_entry(entry: Any) -> tuple[str, str, int]:
    if not isinstance(entry, Mapping):
        raise ValueError("manifest bundle_contents entry must be a mapping")

    rel = str(entry.get("path", "")).strip()
    digest = str(entry.get("sha256", "")).strip().lower()
    size = entry.get("size")

    if (
        not rel
        or rel.startswith("/")
        or "\\" in rel
        or rel in {".", ".."}
        or any(part in {"", ".", ".."} for part in rel.split("/"))
    ):
        raise ValueError("manifest bundle_contents contains an invalid path")
    if (
        len(digest) != 64
        or any(ch not in "0123456789abcdef" for ch in digest)
    ):
        raise ValueError("manifest bundle_contents contains an invalid sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("manifest bundle_contents contains an invalid size")
    return rel, digest, size


def _verify_declared_bundle_contents(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    required: bool,
) -> tuple[dict[str, bytes], bool]:
    raw_entries = manifest.get("bundle_contents")
    if not isinstance(raw_entries, list) or not raw_entries:
        if required:
            raise ValueError(
                "manifest bundle_contents is required for verified runtime loading"
            )
        logger.warning(
            "legacy policy bundle has no bundle_contents; exact body binding "
            "is not established in non-strict compatibility mode"
        )
        return {}, False

    declared: dict[str, tuple[str, int]] = {}
    for raw_entry in raw_entries:
        rel, digest, size = _validate_manifest_bundle_entry(raw_entry)
        if rel in declared:
            raise ValueError("manifest bundle_contents contains duplicate paths")
        declared[rel] = (digest, size)

    actual: dict[str, bytes] = {}
    for candidate in root.rglob("*"):
        rel = candidate.relative_to(root).as_posix()
        if rel in {"manifest.json", "manifest.sig"} or rel.endswith(".tar.gz"):
            continue
        if candidate.is_symlink():
            raise ValueError("policy bundle contains a symlink")
        if not candidate.is_file():
            continue
        try:
            actual[rel] = candidate.read_bytes()
        except OSError as exc:
            raise ValueError("failed to read declared policy bundle content") from exc

    if set(actual) != set(declared):
        raise ValueError("policy bundle contents do not match signed manifest")

    for rel, payload in actual.items():
        expected_digest, expected_size = declared[rel]
        actual_digest = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ValueError(
                f"policy bundle content digest mismatch: {rel}"
            )
        if len(payload) != expected_size:
            raise ValueError(
                f"policy bundle content size mismatch: {rel}"
            )

    required_ir = "compiled/canonical_ir.json"
    if required_ir not in actual:
        raise ValueError("policy bundle is missing compiled/canonical_ir.json")
    return actual, True


def adapt_canonical_ir(canonical_ir: CanonicalPolicyIR) -> RuntimePolicy:
    """Convert canonical policy IR mapping into a runtime-ready policy object."""
    try:
        return RuntimePolicy(
            policy_id=canonical_ir["policy_id"],
            version=canonical_ir["version"],
            title=canonical_ir["title"],
            description=canonical_ir["description"],
            effective_date=canonical_ir.get("effective_date"),
            scope={
                "domains": list(canonical_ir["scope"]["domains"]),
                "routes": list(canonical_ir["scope"]["routes"]),
                "actors": list(canonical_ir["scope"]["actors"]),
            },
            conditions=[dict(item) for item in canonical_ir["conditions"]],
            constraints=[dict(item) for item in canonical_ir["constraints"]],
            requirements=dict(canonical_ir["requirements"]),
            outcome=dict(canonical_ir["outcome"]),
            obligations=list(canonical_ir["obligations"]),
            test_vectors=[dict(item) for item in canonical_ir["test_vectors"]],
            metadata=dict(canonical_ir.get("metadata", {})),
            source_refs=list(canonical_ir.get("source_refs", [])),
        )
    except KeyError as exc:
        raise ValueError(
            f"canonical IR missing required key {exc}"
        ) from exc
    except (TypeError, AttributeError) as exc:
        raise ValueError(
            f"canonical IR structure invalid: {exc}"
        ) from exc


def load_runtime_bundle(
    bundle_dir: str | Path,
    *,
    public_key_pem: bytes | None = None,
) -> RuntimePolicyBundle:
    """Load and verify the exact policy bytes that will be evaluated.

    Strict posture requires successful Ed25519 verification with trusted key
    material. Signed manifest metadata is then checked against the exact bundle
    files loaded into memory, including canonical-IR digest, semantic hash,
    policy id and version. The same canonical-IR bytes that pass these checks
    are adapted for runtime evaluation.
    """
    is_strict = _active_policy_posture_is_strict()
    require_ed25519 = _ed25519_required(is_strict=is_strict)

    root = Path(bundle_dir)
    manifest_path = root / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise ValueError("failed to read policy manifest") from exc
    manifest = _parse_json_mapping_bytes(
        manifest_bytes,
        label="manifest.json",
    )

    signing = manifest.get("signing", {})
    if not isinstance(signing, Mapping):
        raise ValueError("manifest signing metadata must be a mapping")
    signing_algorithm = str(signing.get("algorithm", "")).strip().lower()
    if signing_algorithm not in {"ed25519", "sha256"}:
        raise ValueError("unsupported manifest signing algorithm")

    if require_ed25519 and signing_algorithm != "ed25519":
        raise ValueError(
            "bundle does not use Ed25519 signing required by secure/prod posture"
        )

    signature_path = root / "manifest.sig"
    verification = ManifestVerificationResult(
        integrity_verified=False,
        signature_verified=False,
        algorithm=signing_algorithm,
        signer_id="",
    )
    if not signature_path.exists():
        if signing_algorithm == "ed25519" or require_ed25519:
            raise ValueError(
                "bundle is missing manifest.sig; verified Ed25519 policy "
                "artifacts are required"
            )
        logger.warning(
            "policy bundle is missing manifest.sig; accepting unsigned artifact "
            "only in non-strict legacy compatibility mode"
        )
    else:
        try:
            signature_text = signature_path.read_text(
                encoding="utf-8"
            ).strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError("failed to read policy manifest signature") from exc
        verification = _verify_manifest_payload(
            manifest_bytes=manifest_bytes,
            manifest=manifest,
            signature_text=signature_text,
            public_key_pem=public_key_pem,
            require_ed25519=require_ed25519,
        )
        if not verification.integrity_verified:
            raise ValueError("manifest signature verification failed")

    payloads, contents_verified = _verify_declared_bundle_contents(
        root,
        manifest,
        required=is_strict or verification.signature_verified,
    )

    if contents_verified:
        canonical_bytes = payloads["compiled/canonical_ir.json"]
    else:
        try:
            canonical_bytes = (
                root / "compiled" / "canonical_ir.json"
            ).read_bytes()
        except OSError as exc:
            raise ValueError("failed to read canonical policy IR") from exc

    canonical_ir = _parse_json_mapping_bytes(
        canonical_bytes,
        label="compiled/canonical_ir.json",
    )

    if contents_verified:
        computed_semantic_hash = semantic_policy_hash(canonical_ir)
        manifest_semantic_hash = str(
            manifest.get("semantic_hash", "")
        ).strip().lower()
        if not manifest_semantic_hash or not hmac.compare_digest(
            computed_semantic_hash,
            manifest_semantic_hash,
        ):
            raise ValueError("policy semantic_hash does not match canonical IR")

        manifest_policy_id = str(manifest.get("policy_id", ""))
        manifest_version = str(manifest.get("version", ""))
        canonical_policy_id = str(canonical_ir.get("policy_id", ""))
        canonical_version = str(canonical_ir.get("version", ""))
        if manifest_policy_id != canonical_policy_id:
            raise ValueError("manifest policy_id does not match canonical IR")
        if manifest_version != canonical_version:
            raise ValueError("manifest version does not match canonical IR")
        effective_semantic_hash = computed_semantic_hash
    else:
        effective_semantic_hash = str(manifest.get("semantic_hash", ""))

    runtime_policy = adapt_canonical_ir(canonical_ir)

    logger.info(
        "bundle loaded: policy_id=%s version=%s hash=%s signing=%s "
        "signature_verified=%s contents_verified=%s",
        runtime_policy.policy_id,
        runtime_policy.version,
        effective_semantic_hash,
        verification.algorithm,
        verification.signature_verified,
        contents_verified,
    )

    return RuntimePolicyBundle(
        schema_version=str(manifest.get("schema_version", "0.1")),
        policy_id=runtime_policy.policy_id,
        version=runtime_policy.version,
        semantic_hash=effective_semantic_hash,
        compiler_version=str(manifest.get("compiler_version", "")),
        compiled_at=str(manifest.get("compiled_at", "")),
        runtime_policies=[runtime_policy],
        manifest=manifest,
        manifest_integrity_verified=verification.integrity_verified,
        signature_verified=verification.signature_verified,
        signature_algorithm=verification.algorithm,
        signer_id=verification.signer_id,
        bundle_contents_verified=contents_verified,
    )


def adapt_compiled_payload(
    *,
    canonical_ir: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> RuntimePolicyBundle:
    """Adapt in-memory compiled payloads (useful for API/pipeline integration)."""
    runtime_policy = adapt_canonical_ir(dict(canonical_ir))
    return RuntimePolicyBundle(
        schema_version=str(manifest.get("schema_version", "0.1")),
        policy_id=runtime_policy.policy_id,
        version=runtime_policy.version,
        semantic_hash=str(manifest.get("semantic_hash", "")),
        compiler_version=str(manifest.get("compiler_version", "")),
        compiled_at=str(manifest.get("compiled_at", "")),
        runtime_policies=[runtime_policy],
        manifest=dict(manifest),
        manifest_integrity_verified=False,
        signature_verified=False,
        signature_algorithm="",
        signer_id="",
        bundle_contents_verified=False,
    )
