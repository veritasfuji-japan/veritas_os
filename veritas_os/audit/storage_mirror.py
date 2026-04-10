"""TrustLog mirror backend abstractions.

This module provides pluggable append-only mirror backends used by the
signed TrustLog writer. Backends return a normalized status dict so caller
logic can consistently enforce hard-fail posture semantics.
"""

from __future__ import annotations

import importlib
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class StorageMirror(ABC):
    """Abstract append-only TrustLog mirror backend."""

    backend_name: str

    @abstractmethod
    def append_line(self, line: str) -> Dict[str, Any]:
        """Append one serialized JSONL line and return mirror status metadata."""


class LocalAppendMirror(StorageMirror):
    """Append line-oriented mirror backend for local WORM-like filesystems."""

    backend_name = "local"

    def __init__(
        self,
        *,
        path: Optional[Path],
        append_fn: Callable[[Path, str], None],
    ) -> None:
        self.path = path
        self._append_fn = append_fn

    def append_line(self, line: str) -> Dict[str, Any]:
        if self.path is None:
            return {
                "configured": False,
                "ok": False,
                "backend": self.backend_name,
                "path": None,
            }

        try:
            self._append_fn(self.path, line)
        except OSError as exc:
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "path": str(self.path),
                "error": f"{exc.__class__.__name__}: {exc}",
            }

        return {
            "configured": True,
            "ok": True,
            "backend": self.backend_name,
            "path": str(self.path),
        }


class S3ObjectLockMirror(StorageMirror):
    """Append-only S3 mirror backend with optional Object Lock retention.

    Security warning:
        This backend performs network writes to AWS S3. Ensure IAM principals
        only have least-privilege permissions on the configured bucket/prefix.
    """

    backend_name = "s3_object_lock"

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: Optional[str] = None,
        object_lock_mode: Optional[str] = None,
        retention_days: Optional[int] = None,
        s3_client: Optional[object] = None,
    ) -> None:
        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")
        self.region = (region or "").strip() or None
        self.object_lock_mode = (object_lock_mode or "").strip() or None
        self.retention_days = retention_days
        self._s3_client = s3_client

    @property
    def s3_client(self) -> object:
        """Lazily construct boto3 S3 client."""
        if self._s3_client is None:
            boto3 = importlib.import_module("boto3")
            kwargs: Dict[str, Any] = {}
            if self.region:
                kwargs["region_name"] = self.region
            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    def _build_key(self) -> str:
        now = datetime.now(timezone.utc)
        suffix = uuid.uuid4().hex
        key = f"trustlog/{now.strftime('%Y/%m/%d/%H/%M/%S')}-{suffix}.jsonl"
        if not self.prefix:
            return key
        return f"{self.prefix}/{key}"

    def append_line(self, line: str) -> Dict[str, Any]:
        if not self.bucket:
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "error": "ValueError: VERITAS_TRUSTLOG_S3_BUCKET is required",
            }

        key = self._build_key()
        put_kwargs: Dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": line.encode("utf-8"),
            "ContentType": "application/x-ndjson",
        }
        retain_until_date: Optional[str] = None
        if self.object_lock_mode:
            put_kwargs["ObjectLockMode"] = self.object_lock_mode
        if self.retention_days and self.retention_days > 0:
            retain_until = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
            retain_until_date = retain_until.isoformat().replace("+00:00", "Z")
            put_kwargs["ObjectLockRetainUntilDate"] = retain_until

        try:
            response = self.s3_client.put_object(**put_kwargs)
        except Exception as exc:  # noqa: BLE001
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "bucket": self.bucket,
                "key": key,
                "error": f"{exc.__class__.__name__}: {exc}",
            }

        return {
            "configured": True,
            "ok": True,
            "backend": self.backend_name,
            "bucket": self.bucket,
            "key": key,
            "version_id": response.get("VersionId"),
            "etag": response.get("ETag"),
            "retention_mode": self.object_lock_mode,
            "retain_until_date": retain_until_date,
        }


def build_storage_mirror(*, append_fn: Callable[[Path, str], None]) -> StorageMirror:
    """Build configured TrustLog mirror backend from environment variables."""
    backend = os.getenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local").strip().lower()

    if backend == "local":
        mirror_path = os.getenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "").strip()
        return LocalAppendMirror(path=Path(mirror_path) if mirror_path else None, append_fn=append_fn)

    if backend == "s3_object_lock":
        bucket = os.getenv("VERITAS_TRUSTLOG_S3_BUCKET", "")
        prefix = os.getenv("VERITAS_TRUSTLOG_S3_PREFIX", "")
        region = os.getenv("VERITAS_TRUSTLOG_S3_REGION", "")
        object_lock_mode = os.getenv("VERITAS_TRUSTLOG_S3_OBJECT_LOCK_MODE", "")
        retention_days_raw = os.getenv("VERITAS_TRUSTLOG_S3_RETENTION_DAYS", "").strip()
        retention_days: Optional[int] = None
        if retention_days_raw:
            retention_days = int(retention_days_raw)
        return S3ObjectLockMirror(
            bucket=bucket,
            prefix=prefix,
            region=region,
            object_lock_mode=object_lock_mode,
            retention_days=retention_days,
        )

    raise ValueError("Unsupported mirror backend. Expected 'local' or 's3_object_lock'.")
