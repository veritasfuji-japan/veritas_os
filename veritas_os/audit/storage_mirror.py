"""TrustLog mirror backend abstractions.

This module provides pluggable append-only mirror backends used by the
signed TrustLog writer. Backends return a normalized status dict so caller
logic can consistently enforce hard-fail posture semantics.
"""

from __future__ import annotations

import importlib
import hmac
import json
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from veritas_os.security.hash import canonical_json_dumps, sha256_hex, sha256_of_canonical_json


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
        mirror_mode: str = "single_entry_objects",
        segment_max_entries: int = 100,
        manifest_hmac_key: Optional[str] = None,
        region: Optional[str] = None,
        object_lock_mode: Optional[str] = None,
        retention_days: Optional[int] = None,
        s3_client: Optional[object] = None,
    ) -> None:
        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")
        self.mirror_mode = mirror_mode.strip().lower()
        self.segment_max_entries = max(1, int(segment_max_entries))
        self.manifest_hmac_key = (manifest_hmac_key or "").strip() or None
        self.region = (region or "").strip() or None
        self.object_lock_mode = (object_lock_mode or "").strip() or None
        self.retention_days = retention_days
        self._s3_client = s3_client
        self._segment_lines: list[str] = []
        self._segment_entries: list[Dict[str, Any]] = []

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
        if self.mirror_mode == "sealed_segments":
            return self._build_segment_key(segment_id=uuid.uuid4().hex)
        now = datetime.now(timezone.utc)
        suffix = uuid.uuid4().hex
        key = f"trustlog/{now.strftime('%Y/%m/%d/%H/%M/%S')}-{suffix}.jsonl"
        if not self.prefix:
            return key
        return f"{self.prefix}/{key}"

    def _build_segment_key(self, *, segment_id: str) -> str:
        now = datetime.now(timezone.utc)
        key = f"trustlog/segments/{now.strftime('%Y/%m/%d')}/segment-{segment_id}.jsonl"
        if not self.prefix:
            return key
        return f"{self.prefix}/{key}"

    def _build_manifest_key(self, *, segment_id: str) -> str:
        now = datetime.now(timezone.utc)
        key = f"trustlog/segments/{now.strftime('%Y/%m/%d')}/manifest-{segment_id}.json"
        if not self.prefix:
            return key
        return f"{self.prefix}/{key}"

    @staticmethod
    def _entry_hash(entry: Dict[str, Any], line: str) -> str:
        if isinstance(entry.get("payload_hash"), str) and entry["payload_hash"]:
            return str(entry["payload_hash"])
        return sha256_hex(line)

    def _build_manifest(
        self,
        *,
        segment_id: str,
        segment_payload_hash: str,
        segment_object_key: str,
        manifest_key: str,
    ) -> Dict[str, Any]:
        first_entry = self._segment_entries[0]
        last_entry = self._segment_entries[-1]
        manifest: Dict[str, Any] = {
            "segment_id": segment_id,
            "entry_count": len(self._segment_entries),
            "first_timestamp": first_entry.get("timestamp"),
            "last_timestamp": last_entry.get("timestamp"),
            "first_hash": self._entry_hash(first_entry, self._segment_lines[0]),
            "last_hash": self._entry_hash(last_entry, self._segment_lines[-1]),
            "segment_payload_hash": segment_payload_hash,
            "object_keys_written": [segment_object_key, manifest_key],
        }
        if self.manifest_hmac_key:
            signature = hmac.new(
                self.manifest_hmac_key.encode("utf-8"),
                canonical_json_dumps(manifest).encode("utf-8"),
                "sha256",
            ).hexdigest()
            manifest["manifest_signature"] = signature
        return manifest

    def _put_object(self, *, key: str, body: bytes, content_type: str) -> Dict[str, Any]:
        put_kwargs: Dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": body,
            "ContentType": content_type,
        }
        if self.object_lock_mode:
            put_kwargs["ObjectLockMode"] = self.object_lock_mode
        if self.retention_days and self.retention_days > 0:
            retain_until = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
            put_kwargs["ObjectLockRetainUntilDate"] = retain_until
        return self.s3_client.put_object(**put_kwargs)

    def _append_sealed_segment(self, line: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "error": "ValueError: sealed_segments mode requires JSON line entries",
            }

        if not isinstance(parsed, dict):
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "error": "ValueError: sealed_segments mode requires JSON object entries",
            }

        self._segment_lines.append(line)
        self._segment_entries.append(parsed)

        if len(self._segment_lines) < self.segment_max_entries:
            return {
                "configured": True,
                "ok": True,
                "backend": self.backend_name,
                "bucket": self.bucket,
                "mode": "sealed_segments",
                "segment_sealed": False,
                "pending_entry_count": len(self._segment_lines),
            }

        segment_id = uuid.uuid4().hex
        segment_payload = "".join(self._segment_lines)
        segment_payload_hash = sha256_hex(segment_payload)
        segment_key = self._build_segment_key(segment_id=segment_id)
        manifest_key = self._build_manifest_key(segment_id=segment_id)
        manifest = self._build_manifest(
            segment_id=segment_id,
            segment_payload_hash=segment_payload_hash,
            segment_object_key=segment_key,
            manifest_key=manifest_key,
        )
        manifest_hash = sha256_of_canonical_json(manifest)
        manifest_payload = canonical_json_dumps(manifest).encode("utf-8")
        retain_until_date: Optional[str] = None
        if self.retention_days and self.retention_days > 0:
            retain_until = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
            retain_until_date = retain_until.isoformat().replace("+00:00", "Z")

        try:
            segment_response = self._put_object(
                key=segment_key,
                body=segment_payload.encode("utf-8"),
                content_type="application/x-ndjson",
            )
            manifest_response = self._put_object(
                key=manifest_key,
                body=manifest_payload,
                content_type="application/json",
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "bucket": self.bucket,
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        finally:
            self._segment_lines = []
            self._segment_entries = []

        return {
            "configured": True,
            "ok": True,
            "backend": self.backend_name,
            "bucket": self.bucket,
            "mode": "sealed_segments",
            "segment_sealed": True,
            "retention_mode": self.object_lock_mode,
            "retain_until_date": retain_until_date,
            "segment_id": segment_id,
            "segment_object_key": segment_key,
            "segment_manifest_key": manifest_key,
            "segment_payload_hash": segment_payload_hash,
            "manifest_hash": manifest_hash,
            "manifest_version_id": manifest_response.get("VersionId"),
            "manifest_etag": manifest_response.get("ETag"),
            "version_id": segment_response.get("VersionId"),
            "etag": segment_response.get("ETag"),
            "manifest": manifest,
        }

    def append_line(self, line: str) -> Dict[str, Any]:
        if not self.bucket:
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "error": "ValueError: VERITAS_TRUSTLOG_S3_BUCKET is required",
            }
        if self.mirror_mode not in {"single_entry_objects", "sealed_segments"}:
            return {
                "configured": True,
                "ok": False,
                "backend": self.backend_name,
                "error": (
                    "ValueError: VERITAS_TRUSTLOG_S3_MIRROR_MODE must be "
                    "'single_entry_objects' or 'sealed_segments'"
                ),
            }
        if self.mirror_mode == "sealed_segments":
            return self._append_sealed_segment(line)

        key = self._build_key()
        retain_until_date: Optional[str] = None
        if self.retention_days and self.retention_days > 0:
            retain_until = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
            retain_until_date = retain_until.isoformat().replace("+00:00", "Z")

        try:
            response = self._put_object(
                key=key,
                body=line.encode("utf-8"),
                content_type="application/x-ndjson",
            )
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
            "mode": "single_entry_objects",
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
        mirror_mode = os.getenv("VERITAS_TRUSTLOG_S3_MIRROR_MODE", "single_entry_objects")
        segment_max_entries_raw = os.getenv("VERITAS_TRUSTLOG_S3_SEGMENT_MAX_ENTRIES", "100")
        segment_max_entries = int(segment_max_entries_raw)
        manifest_hmac_key = os.getenv("VERITAS_TRUSTLOG_S3_SEGMENT_MANIFEST_HMAC_KEY", "")
        object_lock_mode = os.getenv("VERITAS_TRUSTLOG_S3_OBJECT_LOCK_MODE", "")
        retention_days_raw = os.getenv("VERITAS_TRUSTLOG_S3_RETENTION_DAYS", "").strip()
        retention_days: Optional[int] = None
        if retention_days_raw:
            retention_days = int(retention_days_raw)
        return S3ObjectLockMirror(
            bucket=bucket,
            prefix=prefix,
            mirror_mode=mirror_mode,
            segment_max_entries=segment_max_entries,
            manifest_hmac_key=manifest_hmac_key,
            region=region,
            object_lock_mode=object_lock_mode,
            retention_days=retention_days,
        )

    raise ValueError("Unsupported mirror backend. Expected 'local' or 's3_object_lock'.")
