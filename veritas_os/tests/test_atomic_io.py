# veritas_os/tests/test_atomic_io.py
"""Tests for atomic file write utilities."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.atomic_io import (
    atomic_write_text,
    atomic_write_json,
    atomic_append_line,
)


class TestAtomicWriteText:
    """Tests for atomic_write_text function."""

    def test_basic_write(self, tmp_path: Path):
        """Test basic text file write."""
        target = tmp_path / "test.txt"
        content = "Hello, World!"

        atomic_write_text(target, content)

        assert target.exists()
        assert target.read_text() == content

    def test_overwrites_existing(self, tmp_path: Path):
        """Test that existing file is overwritten atomically."""
        target = tmp_path / "test.txt"
        target.write_text("old content")

        atomic_write_text(target, "new content")

        assert target.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Test that parent directories are created."""
        target = tmp_path / "a" / "b" / "c" / "test.txt"

        atomic_write_text(target, "nested content")

        assert target.exists()
        assert target.read_text() == "nested content"

    def test_unicode_content(self, tmp_path: Path):
        """Test writing unicode content."""
        target = tmp_path / "unicode.txt"
        content = "日本語テスト 🚀"

        atomic_write_text(target, content)

        assert target.read_text(encoding="utf-8") == content

    def test_no_temp_file_left_on_success(self, tmp_path: Path):
        """Test that no temp files are left after successful write."""
        target = tmp_path / "test.txt"

        atomic_write_text(target, "content")

        # Check no temp files remain
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.txt"

    def test_no_temp_file_left_on_failure(self, tmp_path: Path):
        """Test that temp files are cleaned up on failure."""
        target = tmp_path / "test.txt"

        # Make write fail by making content non-encodable
        with mock.patch("os.write", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_write_text(target, "content")

        # Check no temp files remain (and target wasn't created)
        files = list(tmp_path.iterdir())
        assert len(files) == 0

    def test_accepts_string_path(self, tmp_path: Path):
        """Test that string paths are accepted."""
        target = str(tmp_path / "test.txt")

        atomic_write_text(target, "content")

        assert Path(target).read_text() == "content"

    def test_handles_partial_os_write(self, tmp_path: Path):
        """Test robustness when os.write writes only part of the buffer."""
        target = tmp_path / "partial.txt"
        payload = "abcdefghijklmnopqrstuvwxyz"

        original_write = os.write

        def partial_write(fd: int, data: bytes) -> int:
            if len(data) > 4:
                return original_write(fd, data[:4])
            return original_write(fd, data)

        with mock.patch("os.write", side_effect=partial_write):
            atomic_write_text(target, payload)

        assert target.read_text() == payload


class TestAtomicWriteJson:
    """Tests for atomic_write_json function."""

    def test_basic_json_write(self, tmp_path: Path):
        """Test basic JSON write."""
        target = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        atomic_write_json(target, data)

        assert target.exists()
        loaded = json.loads(target.read_text())
        assert loaded == data

    def test_indent_option(self, tmp_path: Path):
        """Test indentation option."""
        target = tmp_path / "test.json"
        data = {"a": 1}

        # With indent
        atomic_write_json(target, data, indent=2)
        content_indented = target.read_text()
        assert "\n" in content_indented

        # Without indent
        atomic_write_json(target, data, indent=None)
        content_compact = target.read_text()
        # Compact should be shorter (less whitespace)
        assert len(content_compact) < len(content_indented)

    def test_ensure_ascii_false(self, tmp_path: Path):
        """Test that non-ASCII chars are preserved by default."""
        target = tmp_path / "test.json"
        data = {"message": "日本語"}

        atomic_write_json(target, data)

        content = target.read_text()
        assert "日本語" in content

    def test_trailing_newline(self, tmp_path: Path):
        """Test that output has trailing newline."""
        target = tmp_path / "test.json"

        atomic_write_json(target, {"a": 1})

        content = target.read_text()
        assert content.endswith("\n")

    def test_complex_nested_data(self, tmp_path: Path):
        """Test writing complex nested data."""
        target = tmp_path / "test.json"
        data = {
            "items": [1, 2, {"nested": True}],
            "metadata": {"created": "2025-01-01"},
        }

        atomic_write_json(target, data)

        loaded = json.loads(target.read_text())
        assert loaded == data


class TestAtomicAppendLine:
    """Tests for atomic_append_line function."""

    def test_append_to_new_file(self, tmp_path: Path):
        """Test appending to a new file."""
        target = tmp_path / "test.log"

        atomic_append_line(target, "line1")

        assert target.read_text() == "line1\n"

    def test_append_multiple_lines(self, tmp_path: Path):
        """Test appending multiple lines."""
        target = tmp_path / "test.log"

        atomic_append_line(target, "line1")
        atomic_append_line(target, "line2")
        atomic_append_line(target, "line3")

        lines = target.read_text().splitlines()
        assert lines == ["line1", "line2", "line3"]

    def test_appends_newline_if_missing(self, tmp_path: Path):
        """Test that newline is added if missing."""
        target = tmp_path / "test.log"

        atomic_append_line(target, "no newline")

        content = target.read_text()
        assert content == "no newline\n"

    def test_preserves_existing_newline(self, tmp_path: Path):
        """Test that existing newline is not doubled."""
        target = tmp_path / "test.log"

        atomic_append_line(target, "has newline\n")

        content = target.read_text()
        assert content == "has newline\n"

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Test that parent directories are created."""
        target = tmp_path / "a" / "b" / "test.log"

        atomic_append_line(target, "line")

        assert target.exists()
        assert target.read_text() == "line\n"

    def test_append_handles_partial_os_write(self, tmp_path: Path):
        """Test append durability when os.write performs partial writes."""
        target = tmp_path / "partial.log"
        payload = "line-with-partial-write"

        original_write = os.write

        def partial_write(fd: int, data: bytes) -> int:
            if len(data) > 3:
                return original_write(fd, data[:3])
            return original_write(fd, data)

        with mock.patch("os.write", side_effect=partial_write):
            atomic_append_line(target, payload)

        assert target.read_text() == f"{payload}\n"


class TestAtomicWriteNpz:
    """Tests for atomic_write_npz function."""

    def test_basic_npz_write(self, tmp_path: Path):
        """Test basic NPZ write."""
        pytest.importorskip("numpy")
        import numpy as np
        from veritas_os.core.atomic_io import atomic_write_npz

        target = tmp_path / "test.npz"
        vecs = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
        ids = np.array(["a", "b"], dtype=object)

        atomic_write_npz(target, vecs=vecs, ids=ids)

        assert target.exists()
        loaded = np.load(target, allow_pickle=True)
        np.testing.assert_array_equal(loaded["vecs"], vecs)
        np.testing.assert_array_equal(loaded["ids"], ids)

    def test_no_temp_file_left(self, tmp_path: Path):
        """Test that no temp files are left after successful write."""
        pytest.importorskip("numpy")
        import numpy as np
        from veritas_os.core.atomic_io import atomic_write_npz

        target = tmp_path / "test.npz"
        vecs = np.array([[1, 2]], dtype=np.float32)

        atomic_write_npz(target, vecs=vecs)

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.npz"

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Test that parent directories are created."""
        pytest.importorskip("numpy")
        import numpy as np
        from veritas_os.core.atomic_io import atomic_write_npz

        target = tmp_path / "a" / "b" / "test.npz"
        vecs = np.array([[1, 2]], dtype=np.float32)

        atomic_write_npz(target, vecs=vecs)

        assert target.exists()


class TestAtomicityGuarantee:
    """Tests to verify atomicity behavior."""

    def test_original_preserved_on_write_failure(self, tmp_path: Path):
        """Test that original file is preserved if write fails."""
        target = tmp_path / "test.txt"
        original_content = "original content"
        target.write_text(original_content)

        # Mock os.replace to simulate failure after temp file is written
        with mock.patch("os.replace", side_effect=OSError("permission denied")):
            with pytest.raises(OSError):
                atomic_write_text(target, "new content")

        # Original should be unchanged
        assert target.read_text() == original_content

    def test_fsync_called(self, tmp_path: Path):
        """Test that fsync is called for durability."""
        target = tmp_path / "test.txt"

        with mock.patch("os.fsync") as mock_fsync:
            atomic_write_text(target, "content")

        mock_fsync.assert_called()


class TestAtomicWriteNpzFsync:
    """
    Tests for C-2 fix: atomic_write_npz() should call fsync.

    ★ C-2: np.savez() 後に fsync しないと、クラッシュ時に
    ベクトルインデックスが破損する可能性がある問題を修正。
    """

    def test_fsync_called_for_npz(self, tmp_path: Path):
        """Test that fsync is called after np.savez in atomic_write_npz."""
        pytest.importorskip("numpy")
        import numpy as np
        from veritas_os.core.atomic_io import atomic_write_npz

        target = tmp_path / "test.npz"
        vecs = np.array([[1, 2, 3]], dtype=np.float32)

        with mock.patch("os.fsync") as mock_fsync:
            atomic_write_npz(target, vecs=vecs)

        # fsync should be called at least once (for the file and possibly directory)
        assert mock_fsync.call_count >= 1, \
            f"fsync should be called at least once, but was called {mock_fsync.call_count} times"

    def test_npz_file_is_complete(self, tmp_path: Path):
        """Test that the npz file is complete and readable after write."""
        pytest.importorskip("numpy")
        import numpy as np
        from veritas_os.core.atomic_io import atomic_write_npz

        target = tmp_path / "test.npz"
        original_vecs = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
        original_ids = np.array(["a", "b"], dtype=object)

        atomic_write_npz(target, vecs=original_vecs, ids=original_ids)

        # File should exist and be readable
        assert target.exists()
        loaded = np.load(target, allow_pickle=True)
        np.testing.assert_array_equal(loaded["vecs"], original_vecs)
        np.testing.assert_array_equal(loaded["ids"], original_ids)
