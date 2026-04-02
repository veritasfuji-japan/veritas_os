"""Policy compiler for canonical IR + manifest + bundle artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
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


def _manifest_signature_hex(manifest_path: Path) -> str:
    """Return deterministic SHA-256 signature hex for manifest payload."""
    payload = manifest_path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def compile_policy_to_bundle(
    source_policy_path: str | Path,
    output_dir: str | Path,
    *,
    compiled_at: str | None = None,
    compiler_version: str = COMPILER_VERSION,
) -> CompileResult:
    """Compile a source policy into deterministic bundle artifacts."""
    source_path = Path(source_policy_path)
    out_dir = Path(output_dir)

    policy = load_and_validate_policy(source_path)
    canonical_ir = to_canonical_ir(policy)
    semantic_hash = semantic_policy_hash(canonical_ir)

    policy_dir = out_dir / canonical_ir["policy_id"] / canonical_ir["version"]
    bundle_dir = policy_dir / "bundle"

    try:
        bundle_dir.mkdir(parents=True, exist_ok=True)

        canonical_path = bundle_dir / "compiled" / "canonical_ir.json"
        explain_path = bundle_dir / "compiled" / "explain.json"
        unsigned_path = bundle_dir / "signatures" / "UNSIGNED"

        write_stable_json(canonical_path, canonical_ir)
        explanation_metadata: Dict[str, Any] = build_explanation_metadata(canonical_ir)
        write_stable_json(explain_path, explanation_metadata)
        unsigned_path.parent.mkdir(parents=True, exist_ok=True)
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
        )
        manifest_path = bundle_dir / "manifest.json"
        write_stable_json(manifest_path, manifest)
        signature_path = bundle_dir / "manifest.sig"
        signature_path.write_text(_manifest_signature_hex(manifest_path) + "\n", encoding="utf-8")

        archive_path = create_bundle_archive(bundle_dir)
    except OSError as exc:
        raise PolicyCompilationError(
            f"failed to write bundle artifacts: {exc}"
        ) from exc

    return CompileResult(
        bundle_dir=bundle_dir,
        archive_path=archive_path,
        semantic_hash=semantic_hash,
        manifest_path=manifest_path,
    )
