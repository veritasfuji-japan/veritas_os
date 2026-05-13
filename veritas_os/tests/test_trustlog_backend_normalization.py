"""Unit tests for TrustLog backend normalization helpers."""

from veritas_os.security.trustlog_backend_normalization import (
    normalize_trustlog_anchor_backend,
    normalize_trustlog_mirror_backend,
    normalize_trustlog_signer_backend,
)


def test_normalize_trustlog_signer_backend() -> None:
    """Signer backend aliases normalize to canonical runtime values."""
    assert normalize_trustlog_signer_backend(None) == "file"
    assert normalize_trustlog_signer_backend("") == "file"
    assert normalize_trustlog_signer_backend("file") == "file"
    assert normalize_trustlog_signer_backend("file_ed25519") == "file"
    assert normalize_trustlog_signer_backend("aws_kms") == "aws_kms"
    assert normalize_trustlog_signer_backend("aws_kms_ed25519") == "aws_kms"
    assert normalize_trustlog_signer_backend("CUSTOM") == "custom"


def test_normalize_trustlog_mirror_backend() -> None:
    """Mirror backend aliases normalize to canonical runtime values."""
    assert normalize_trustlog_mirror_backend(None) == "local"
    assert normalize_trustlog_mirror_backend("") == "local"
    assert normalize_trustlog_mirror_backend("filesystem") == "local"
    assert normalize_trustlog_mirror_backend("s3") == "s3_object_lock"
    assert normalize_trustlog_mirror_backend("s3_object_lock") == "s3_object_lock"
    assert normalize_trustlog_mirror_backend("unknown_backend") == "unknown_backend"


def test_normalize_trustlog_anchor_backend() -> None:
    """Anchor backend aliases normalize to canonical runtime values."""
    assert normalize_trustlog_anchor_backend(None) == "local"
    assert normalize_trustlog_anchor_backend("") == "local"
    assert normalize_trustlog_anchor_backend("file") == "local"
    assert normalize_trustlog_anchor_backend("none") == "noop"
    assert normalize_trustlog_anchor_backend("noop") == "noop"
    assert normalize_trustlog_anchor_backend("no_op") == "noop"
    assert normalize_trustlog_anchor_backend("tsa") == "tsa"
