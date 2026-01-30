# veritas_os/tests/test_coverage_map_extra.py
"""Additional tests for coverage_map_pipeline.py edge cases."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest

import veritas_os.tools.coverage_map_pipeline as m


class TestCovFileEntryEdgeCases:
    """Test CovFileEntry.from_cov edge cases."""

    def test_missing_lines_non_numeric_skipped(self):
        """Non-numeric values in missing_lines should be skipped."""
        entry = {"missing_lines": [1, "abc", 3, "5"]}
        result = m.CovFileEntry.from_cov(entry)
        # "abc" skipped, numeric strings converted
        assert 1 in result.missing_lines
        assert 3 in result.missing_lines
        assert 5 in result.missing_lines

    def test_missing_lines_with_string_numbers(self):
        """String numeric values should be converted to int."""
        entry = {"missing_lines": ["1", "2", "3"]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_lines == [1, 2, 3]

    def test_missing_lines_with_negative_string(self):
        """Negative string numbers should work."""
        entry = {"missing_lines": ["-1", "10"]}
        result = m.CovFileEntry.from_cov(entry)
        assert -1 in result.missing_lines
        assert 10 in result.missing_lines

    def test_missing_branches_invalid_tuple_skipped(self):
        """Invalid branch tuples (wrong length) should be skipped."""
        entry = {"missing_branches": [[1, 2], [3], [4, 5, 6], [7, 8]]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_branches == [[1, 2], [7, 8]]

    def test_missing_branches_non_convertible_skipped(self):
        """Branches with non-convertible values should be skipped."""
        entry = {"missing_branches": [[1, 2], ["a", "b"], [3, 4]]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_branches == [[1, 2], [3, 4]]

    def test_executed_branches_invalid_skipped(self):
        """Invalid executed_branches should be skipped."""
        entry = {"executed_branches": [[1, 2], [3], "invalid", [4, 5]]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.executed_branches == [[1, 2], [4, 5]]

    def test_empty_entry(self):
        """Empty entry should produce empty lists."""
        result = m.CovFileEntry.from_cov({})
        assert result.missing_lines == []
        assert result.missing_branches == []
        assert result.executed_branches == []

    def test_none_values(self):
        """None values should be treated as empty."""
        entry = {"missing_lines": None, "missing_branches": None, "executed_branches": None}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_lines == []
        assert result.missing_branches == []
        assert result.executed_branches == []


class TestResolveCovJson:
    """Test _resolve_cov_json edge cases."""

    def test_cov_json_relative_path(self, monkeypatch, tmp_path):
        """Test relative COV_JSON path resolution."""
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text("{}", encoding="utf-8")

        # Create a relative path
        rel_path = Path("coverage.json")
        monkeypatch.setattr(m, "COV_JSON", rel_path)

        # Change to tmp_path so relative resolution works
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = m._resolve_cov_json()
            assert result is not None
            assert result.exists()
        finally:
            os.chdir(old_cwd)

    def test_env_variable_resolution(self, monkeypatch, tmp_path):
        """Test VERITAS_COVERAGE_JSON env variable."""
        cov_file = tmp_path / "my_coverage.json"
        cov_file.write_text("{}", encoding="utf-8")

        # Make COV_JSON point to non-existent
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.setenv("VERITAS_COVERAGE_JSON", str(cov_file))

        result = m._resolve_cov_json()
        assert result == cov_file

    def test_env_variable_relative_path(self, monkeypatch, tmp_path):
        """Test relative path in env variable."""
        cov_file = tmp_path / "cov.json"
        cov_file.write_text("{}", encoding="utf-8")

        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            monkeypatch.setenv("VERITAS_COVERAGE_JSON", "cov.json")
            result = m._resolve_cov_json()
            assert result is not None
        finally:
            os.chdir(old_cwd)

    def test_none_when_not_found(self, monkeypatch, tmp_path):
        """Returns None when no coverage.json found."""
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.delenv("VERITAS_COVERAGE_JSON", raising=False)
        monkeypatch.setattr(m, "COV_JSON_CANDIDATES", (tmp_path / "also_nonexistent.json",))

        result = m._resolve_cov_json()
        assert result is None


class TestLoadCov:
    """Test load_cov edge cases."""

    def test_load_cov_not_found(self, monkeypatch, tmp_path, capsys):
        """load_cov returns {} when file not found."""
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.delenv("VERITAS_COVERAGE_JSON", raising=False)
        monkeypatch.setattr(m, "COV_JSON_CANDIDATES", ())

        result = m.load_cov()
        assert result == {}

        captured = capsys.readouterr()
        assert "coverage.json not found" in captured.err

    def test_load_cov_invalid_json(self, monkeypatch, tmp_path, capsys):
        """load_cov returns {} for invalid JSON."""
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text("not valid json {{{", encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.load_cov()
        assert result == {}

        captured = capsys.readouterr()
        assert "failed to parse" in captured.err


class TestFindTargetFile:
    """Test find_target_file edge cases."""

    def test_files_not_dict_raises(self):
        """Raises SystemExit when files is not a dict."""
        cov = {"files": "not a dict"}
        with pytest.raises(SystemExit) as exc:
            m.find_target_file(cov)
        assert "Target not found" in str(exc.value)

    def test_normalized_windows_path_match(self):
        """Test Windows-style path normalization."""
        # Use backslashes like Windows
        cov = {"files": {"C:\\project\\veritas_os\\core\\pipeline.py": {}}}
        # Should still match with forward-slash suffix
        result = m.find_target_file(cov, "veritas_os/core/pipeline.py")
        assert result == "C:\\project\\veritas_os\\core\\pipeline.py"

    def test_non_string_key_skipped(self):
        """Non-string keys are skipped."""
        cov = {"files": {123: {}, "path/veritas_os/core/pipeline.py": {}}}
        result = m.find_target_file(cov)
        assert result == "path/veritas_os/core/pipeline.py"


class TestSafeReadText:
    """Test _safe_read_text edge cases."""

    def test_file_not_found(self, tmp_path, capsys):
        """Returns None for non-existent file."""
        result = m._safe_read_text(tmp_path / "nonexistent.py")
        assert result is None

        captured = capsys.readouterr()
        assert "cannot read source" in captured.err


class TestParseTargetSuffix:
    """Test _parse_target_suffix."""

    def test_default_suffix(self):
        """Returns default when no --target."""
        result = m._parse_target_suffix([])
        assert result == m.TARGET_SUFFIX

    def test_custom_target(self):
        """Returns custom target when specified."""
        result = m._parse_target_suffix(["--target", "custom/path.py"])
        assert result == "custom/path.py"

    def test_invalid_target_usage(self, capsys):
        """Handles invalid --target usage."""
        # --target at end with no value
        result = m._parse_target_suffix(["--target"])
        # Should return default and print error
        assert result == m.TARGET_SUFFIX


class TestMainEdgeCases:
    """Test main() edge cases."""

    def test_main_no_coverage_json(self, monkeypatch, tmp_path, capsys):
        """main() handles missing coverage.json gracefully."""
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.delenv("VERITAS_COVERAGE_JSON", raising=False)
        monkeypatch.setattr(m, "COV_JSON_CANDIDATES", ())

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[pipeline] missing_lines=0" in captured.out
        assert "coverage.json missing or invalid" in captured.out

    def test_main_target_not_found(self, monkeypatch, tmp_path, capsys):
        """main() handles target not found gracefully."""
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text('{"files": {"other.py": {}}}', encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[pipeline] missing_lines=0" in captured.out
        assert "target not found" in captured.out

    def test_main_source_unreadable(self, monkeypatch, tmp_path, capsys):
        """main() handles unreadable source file."""
        # Create coverage.json pointing to non-existent source
        cov = {
            "files": {
                "/nonexistent/veritas_os/core/pipeline.py": {
                    "missing_lines": [1, 2, 3],
                    "missing_branches": [],
                    "executed_branches": []
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)
        monkeypatch.setattr(m, "ROOT", tmp_path)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        # Should still output but note source unreadable
        assert "[pipeline]" in captured.out
        # Missing lines should be grouped under module-level when AST unavailable
        assert "<module-level>" in captured.out

    def test_main_zero_missing_lines(self, monkeypatch, tmp_path, capsys):
        """main() handles case with no missing lines."""
        # Create a valid setup with no missing lines
        pkg = tmp_path / "veritas_os" / "core"
        pkg.mkdir(parents=True)
        src = pkg / "pipeline.py"
        src.write_text("x = 1\n", encoding="utf-8")

        cov = {
            "files": {
                str(src): {
                    "missing_lines": [],
                    "missing_branches": [],
                    "executed_branches": [[1, 2]]
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[pipeline] missing_lines=0" in captured.out

    def test_main_owners_none_with_defs(self, monkeypatch, tmp_path, capsys):
        """main() shows (none) when defs exist but no missing lines."""
        # Create a file with function defs but no missing lines
        pkg = tmp_path / "veritas_os" / "core"
        pkg.mkdir(parents=True)
        src = pkg / "pipeline.py"
        src.write_text("def foo():\n    return 1\n", encoding="utf-8")

        cov = {
            "files": {
                str(src): {
                    "missing_lines": [],
                    "missing_branches": [],
                    "executed_branches": []
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[top owners] (none)" in captured.out

    def test_main_ast_parse_failure(self, monkeypatch, tmp_path, capsys):
        """main() handles AST parse failure gracefully."""
        pkg = tmp_path / "veritas_os" / "core"
        pkg.mkdir(parents=True)
        src = pkg / "pipeline.py"
        # Write invalid Python syntax
        src.write_text("def broken(\n", encoding="utf-8")

        cov = {
            "files": {
                str(src): {
                    "missing_lines": [1],
                    "missing_branches": [],
                    "executed_branches": []
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "AST parse failed" in captured.err
        # Lines should be under module-level when AST fails
        assert "<module-level>" in captured.out


class TestHelperFunctions:
    """Test helper functions."""

    def test_preview_ints_truncation(self):
        """Test _preview_ints truncates long lists."""
        result = m._preview_ints(list(range(20)), max_n=5)
        assert "..." in result
        assert "0, 1, 2, 3, 4" in result

    def test_preview_ints_no_truncation(self):
        """Test _preview_ints doesn't truncate short lists."""
        result = m._preview_ints([1, 2, 3], max_n=5)
        assert "..." not in result
        assert result == "1, 2, 3"

    def test_exit_arcs_filter(self):
        """Test _exit_arcs filters correctly."""
        branches = [[1, 2], [3, -1], [4, 0], [5, 6], [7, -1]]
        result = m._exit_arcs(branches)
        assert result == [[3, -1], [4, 0], [7, -1]]

    def test_eprint(self, capsys):
        """Test _eprint writes to stderr."""
        m._eprint("test message")
        captured = capsys.readouterr()
        assert captured.err == "test message\n"


class TestOwnerFunction:
    """Test owner() function edge cases."""

    def test_owner_module_level(self):
        """Test owner returns module-level for out-of-range lines."""
        defs = [("func1", 5, 10), ("func2", 15, 20)]
        assert m.owner(defs, 1) == "<module-level>"
        assert m.owner(defs, 12) == "<module-level>"
        assert m.owner(defs, 100) == "<module-level>"

    def test_owner_empty_defs(self):
        """Test owner with empty defs."""
        assert m.owner([], 5) == "<module-level>"
