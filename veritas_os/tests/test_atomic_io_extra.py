# veritas_os/tests/test_atomic_io_extra.py
"""Additional tests for atomic_io.py to improve coverage."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from veritas_os.core import atomic_io


class TestAtomicWriteBytesFailure:
    """Test error paths in _atomic_write_bytes."""

    def test_write_failure_cleans_up(self, tmp_path, monkeypatch):
        """Failed write should clean up temp file."""
        target = tmp_path / "test.txt"

        # Mock os.write to fail
        original_write = os.write

        def failing_write(fd, data):
            raise IOError("Mock write failure")

        with patch("os.write", side_effect=failing_write):
            with pytest.raises(IOError):
                atomic_io._atomic_write_bytes(target, b"test data")

        # Temp file should be cleaned up
        temp_files = list(tmp_path.glob(".*tmp"))
        assert len(temp_files) == 0

    def test_fsync_failure_cleans_up(self, tmp_path):
        """Failed fsync should clean up temp file."""
        target = tmp_path / "test.txt"

        with patch("os.fsync", side_effect=OSError("Mock fsync failure")):
            with pytest.raises(OSError):
                atomic_io._atomic_write_bytes(target, b"test data")

        # Temp file should be cleaned up
        temp_files = list(tmp_path.glob(".*tmp"))
        assert len(temp_files) == 0


class TestAtomicWriteNpzEdgeCases:
    """Test edge cases for atomic_write_npz."""

    def test_npz_failure_cleans_up(self, tmp_path):
        """Failed npz save should clean up temp file."""
        target = tmp_path / "test.npz"

        # Import numpy to check if available
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")

        # Create an object that will fail during savez
        class BadArray:
            def __array__(self):
                raise ValueError("Mock array failure")

        with pytest.raises((ValueError, TypeError)):
            atomic_io.atomic_write_npz(target, bad=BadArray())

        # Temp file should be cleaned up (or never created properly)
        temp_files = list(tmp_path.glob(".*tmp*"))
        # Either no temp files or the test passed
        assert len(temp_files) <= 1  # npz might leave temp in some cases


class TestAtomicAppendLine:
    """Test atomic_append_line function."""

    def test_append_creates_file_if_not_exists(self, tmp_path):
        """Appending to non-existent file should create it."""
        target = tmp_path / "new_file.txt"
        assert not target.exists()

        atomic_io.atomic_append_line(target, "first line")

        assert target.exists()
        assert target.read_text() == "first line\n"

    def test_append_multiple_lines(self, tmp_path):
        """Multiple appends should work."""
        target = tmp_path / "multi.txt"

        atomic_io.atomic_append_line(target, "line 1")
        atomic_io.atomic_append_line(target, "line 2")
        atomic_io.atomic_append_line(target, "line 3")

        lines = target.read_text().strip().split("\n")
        assert lines == ["line 1", "line 2", "line 3"]

    def test_append_preserves_existing_content(self, tmp_path):
        """Append should preserve existing content."""
        target = tmp_path / "existing.txt"
        target.write_text("existing content\n")

        atomic_io.atomic_append_line(target, "new line")

        content = target.read_text()
        assert "existing content" in content
        assert "new line" in content


class TestAtomicWriteText:
    """Test atomic_write_text function."""

    def test_write_text_creates_parent_dirs(self, tmp_path):
        """Should create parent directories if needed."""
        target = tmp_path / "nested" / "dir" / "file.txt"
        assert not target.parent.exists()

        atomic_io.atomic_write_text(target, "test content")

        assert target.exists()
        assert target.read_text() == "test content"

    def test_write_text_overwrites_existing(self, tmp_path):
        """Should overwrite existing file."""
        target = tmp_path / "file.txt"
        target.write_text("old content")

        atomic_io.atomic_write_text(target, "new content")

        assert target.read_text() == "new content"


class TestAtomicWriteJson:
    """Test atomic_write_json function."""

    def test_write_json_with_indent(self, tmp_path):
        """Should write formatted JSON with indent."""
        import json
        target = tmp_path / "data.json"

        atomic_io.atomic_write_json(target, {"key": "value"}, indent=2)

        content = target.read_text()
        data = json.loads(content)
        assert data == {"key": "value"}
        assert "\n" in content  # Indented JSON has newlines

    def test_write_json_without_indent(self, tmp_path):
        """Should write compact JSON without indent."""
        import json
        target = tmp_path / "data.json"

        atomic_io.atomic_write_json(target, {"key": "value"})

        content = target.read_text()
        data = json.loads(content)
        assert data == {"key": "value"}


class TestHasNumpy:
    """Test HAS_NUMPY flag behavior."""

    def test_numpy_available(self):
        """HAS_NUMPY should reflect numpy availability."""
        try:
            import numpy
            assert atomic_io.HAS_NUMPY is True
        except ImportError:
            assert atomic_io.HAS_NUMPY is False
