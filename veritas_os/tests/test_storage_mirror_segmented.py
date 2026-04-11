"""Tests for TrustLog S3 mirror segmentation modes."""

from __future__ import annotations

import json

from veritas_os.audit.storage_mirror import S3ObjectLockMirror, build_storage_mirror


class _FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "VersionId": f"v{len(self.calls)}",
            "ETag": f'"etag-{len(self.calls)}"',
        }


def test_single_entry_mode_still_writes_one_object_per_entry() -> None:
    client = _FakeS3Client()
    mirror = S3ObjectLockMirror(
        bucket="trustlog-bucket",
        prefix="audit",
        mirror_mode="single_entry_objects",
        s3_client=client,
    )

    first = mirror.append_line(
        json.dumps({"timestamp": "2026-04-11T00:00:00Z", "payload_hash": "a" * 64}) + "\n"
    )
    second = mirror.append_line(
        json.dumps({"timestamp": "2026-04-11T00:00:01Z", "payload_hash": "b" * 64}) + "\n"
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["mode"] == "single_entry_objects"
    assert second["mode"] == "single_entry_objects"
    assert len(client.calls) == 2


def test_sealed_segment_mode_accumulates_then_seals() -> None:
    client = _FakeS3Client()
    mirror = S3ObjectLockMirror(
        bucket="trustlog-bucket",
        prefix="audit",
        mirror_mode="sealed_segments",
        segment_max_entries=2,
        s3_client=client,
    )

    pending = mirror.append_line(
        json.dumps({"timestamp": "2026-04-11T00:00:00Z", "payload_hash": "a" * 64}) + "\n"
    )
    sealed = mirror.append_line(
        json.dumps({"timestamp": "2026-04-11T00:00:01Z", "payload_hash": "b" * 64}) + "\n"
    )

    assert pending["ok"] is True
    assert pending["segment_sealed"] is False
    assert pending["pending_entry_count"] == 1

    assert sealed["ok"] is True
    assert sealed["segment_sealed"] is True
    assert sealed["mode"] == "sealed_segments"
    assert sealed["segment_object_key"]
    assert sealed["segment_manifest_key"]
    assert sealed["manifest"]["entry_count"] == 2
    assert len(client.calls) == 2


def test_build_storage_mirror_reads_segment_mode_env(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
    monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "trustlog-bucket")
    monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "audit")
    monkeypatch.setenv("VERITAS_TRUSTLOG_S3_MIRROR_MODE", "sealed_segments")
    monkeypatch.setenv("VERITAS_TRUSTLOG_S3_SEGMENT_MAX_ENTRIES", "3")

    mirror = build_storage_mirror(append_fn=lambda path, line: (path, line))

    assert isinstance(mirror, S3ObjectLockMirror)
    assert mirror.mirror_mode == "sealed_segments"
    assert mirror.segment_max_entries == 3
