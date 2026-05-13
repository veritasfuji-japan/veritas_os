"""Pure helpers to normalize TrustLog backend aliases."""

from __future__ import annotations


def _normalized_raw(raw: str | None) -> str:
    """Return stripped lowercase backend value."""
    return (raw or "").strip().lower()


def normalize_trustlog_signer_backend(raw: str | None) -> str:
    """Normalize TrustLog signer backend aliases to canonical names."""
    normalized = _normalized_raw(raw)
    if normalized in {"", "file", "file_ed25519"}:
        return "file"
    if normalized in {"aws_kms", "aws_kms_ed25519"}:
        return "aws_kms"
    return normalized


def normalize_trustlog_mirror_backend(raw: str | None) -> str:
    """Normalize TrustLog mirror backend aliases to canonical names."""
    normalized = _normalized_raw(raw)
    if normalized in {"", "local", "filesystem"}:
        return "local"
    if normalized in {"s3_object_lock", "s3"}:
        return "s3_object_lock"
    return normalized


def normalize_trustlog_anchor_backend(raw: str | None) -> str:
    """Normalize TrustLog anchor backend aliases to canonical names."""
    normalized = _normalized_raw(raw)
    if normalized in {"", "local", "file"}:
        return "local"
    if normalized in {"none", "noop", "no_op"}:
        return "noop"
    return normalized
