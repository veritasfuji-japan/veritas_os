"""Policy compiler for canonical IR + manifest + bundle artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict

from .bundle import collect_bundle_files, create_bundle_archive
from .emit import write_stable_json
from .explain import build_explanation_metadata
from .hash import semantic_policy_hash
from .manifest import build_manifest
from .models import PolicyCompilationError
from .normalize import to_canonical_ir
from .schema import load_and_validate_policy
from .signing import sign_manifest, sha256_manifest_hex

logger = logging.getLogger(__name__)

COMPILER_VERSION = "0.1.0"


@dataclass(frozen=True)
class CompileResult:
    """Compiled bundle output summary."""

    bundle_dir: Path
    archive_path: Path
    semantic_hash: str
    manifest_path: Path


def _utc_now_iso8601() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def compile_policy_to_bundle(
    source_policy_path: str | Path,
    output_dir: str | Path,
    *,
    compiled_at: str | None = None,
    compiler_version: str = COMPILER_VERSION,
    signing_key: bytes | None = None,
) -> CompileResult:
    """Compile a source policy into deterministic bundle artifacts.

    Args:
        signing_key: Optional Ed25519 private key in PEM format.  When
            provided the manifest is signed with Ed25519 (authentic + tamper
            proof).  When ``None`` the legacy SHA-256 hash integrity check is
            used.
    """
    source_path = Path(source_policy_path)
    out_dir = Path(output_dir)

    logger.info(
        "compiling policy: source=%s output=%s",
        source_path,
        out_dir,
    )

    policy = load_and_validate_policy(source_path)
    canonical_ir = to_canonical_ir(policy)
    semantic_hash = semantic_policy_hash(canonical_ir)

    policy_dir = out_dir / canonical_ir["policy_id"] / canonical_ir["version"]
    bundle_dir = policy_dir / "bundle"

    try:
        bundle_dir.mkdir(parents=True, exist_ok=True)

        canonical_path = bundle_dir / "compiled" / "canonical_ir.json"
        explain_path = bundle_dir / "compiled" / "explain.json"
        sig_marker_dir = bundle_dir / "signatures"
        sig_marker_dir.mkdir(parents=True, exist_ok=True)

        write_stable_json(canonical_path, canonical_ir)
        explanation_metadata: Dict[str, Any] = build_explanation_metadata(canonical_ir)
        write_stable_json(explain_path, explanation_metadata)

        use_ed25519 = signing_key is not None
        unsigned_path = sig_marker_dir / "UNSIGNED"
        if not use_ed25519:
            unsigned_path.write_text(
                "signature pending for future signing workflow\n",
                encoding="utf-8",
            )

        bundle_files = collect_bundle_files(bundle_dir)

        manifest = build_manifest(
            canonical_ir,
            semantic_hash=semantic_hash,
            compiler_version=compiler_version,
            compiled_at=compiled_at or _utc_now_iso8601(),
            source_files=[source_path.as_posix()],
            bundle_files=bundle_files,
            signing_algorithm="ed25519" if use_ed25519 else "sha256",
        )
        manifest_path = bundle_dir / "manifest.json"
        write_stable_json(manifest_path, manifest)

        manifest_bytes = manifest_path.read_bytes()
        signature_path = bundle_dir / "manifest.sig"

        if use_ed25519:
            sig_text = sign_manifest(manifest_bytes, signing_key)
            signature_path.write_text(sig_text + "\n", encoding="utf-8")
        else:
            sig_text = sha256_manifest_hex(manifest_bytes)
            signature_path.write_text(sig_text + "\n", encoding="utf-8")

        archive_path = create_bundle_archive(bundle_dir)
    except OSError as exc:
        logger.error(
            "compilation failed for %s: %s",
            source_path,
            exc,
        )
        raise PolicyCompilationError(
            f"failed to write bundle artifacts: {exc}"
        ) from exc

    logger.info(
        "compilation succeeded: policy_id=%s version=%s hash=%s signing=%s",
        canonical_ir["policy_id"],
        canonical_ir["version"],
        semantic_hash,
        "ed25519" if use_ed25519 else "sha256",
    )

    return CompileResult(
        bundle_dir=bundle_dir,
        archive_path=archive_path,
        semantic_hash=semantic_hash,
        manifest_path=manifest_path,
    )
