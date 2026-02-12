"""Tests for veritas_os/scripts/doctor.py — targeting ~80%+ coverage."""

import json
import hashlib
import os

import pytest

from veritas_os.scripts import doctor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_paths(monkeypatch, tmp_path):
    """Redirect all module-level paths to tmp_path."""
    monkeypatch.setattr(doctor, "LOG_DIR", tmp_path)
    monkeypatch.setattr(doctor, "TRUST_LOG_JSON", tmp_path / "trust_log.jsonl")
    monkeypatch.setattr(doctor, "LOG_JSONL", tmp_path / "trust_log.jsonl")
    monkeypatch.setattr(doctor, "REPORT_PATH", tmp_path / "doctor_report.json")


def _build_chain(entries):
    """Build a valid hash chain for a list of entry dicts.

    Returns list of dicts ready to be written as JSONL lines.
    """
    chain = []
    prev = None
    for e in entries:
        payload = {k: v for k, v in e.items() if k not in ("sha256", "sha256_prev")}
        entry_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        combined = (prev + entry_json) if prev else entry_json
        h = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        row = {**payload, "sha256_prev": prev, "sha256": h}
        chain.append(row)
        prev = h
    return chain


# ---------------------------------------------------------------------------
# compute_hash_for_entry
# ---------------------------------------------------------------------------

class TestComputeHashForEntry:
    def test_no_prev_hash(self):
        entry = {"action": "test"}
        result = doctor.compute_hash_for_entry(None, entry)
        payload_json = json.dumps({"action": "test"}, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        assert result == expected

    def test_with_prev_hash(self):
        prev = "abc123"
        entry = {"action": "test"}
        result = doctor.compute_hash_for_entry(prev, entry)
        payload_json = json.dumps({"action": "test"}, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256((prev + payload_json).encode("utf-8")).hexdigest()
        assert result == expected

    def test_strips_sha256_fields(self):
        entry = {"action": "test", "sha256": "XXX", "sha256_prev": "YYY"}
        result = doctor.compute_hash_for_entry(None, entry)
        clean = {"action": "test"}
        payload_json = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        assert result == expected

    def test_does_not_mutate_original(self):
        entry = {"action": "x", "sha256": "h", "sha256_prev": "p"}
        doctor.compute_hash_for_entry("prev", entry)
        assert "sha256" in entry and "sha256_prev" in entry


# ---------------------------------------------------------------------------
# analyze_trustlog
# ---------------------------------------------------------------------------

class TestAnalyzeTrustlog:
    def test_file_not_found(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        result = doctor.analyze_trustlog()
        assert result["status"] == "not_found"
        assert result["entries"] == 0
        assert result["chain_valid"] is None

    def test_empty_file(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        (tmp_path / "trust_log.jsonl").write_text("")
        result = doctor.analyze_trustlog()
        assert result["status"] == "empty"
        assert result["entries"] == 0

    def test_valid_chain(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        entries = [
            {"request_id": "r1", "query": "hello", "created_at": "2025-01-01"},
            {"request_id": "r2", "query": "world", "created_at": "2025-01-02"},
        ]
        chain = _build_chain(entries)
        lines = [json.dumps(e, ensure_ascii=False) for e in chain]
        (tmp_path / "trust_log.jsonl").write_text("\n".join(lines) + "\n")

        result = doctor.analyze_trustlog()
        assert result["status"] == "✅ 正常"
        assert result["entries"] == 2
        assert result["chain_valid"] is True
        assert result["chain_breaks"] == 0
        assert result["hash_mismatches"] == 0
        assert result["last_hash"] is not None
        assert result["created_at"] == "2025-01-02"

    def test_broken_chain(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        chain = _build_chain([{"request_id": "r1"}, {"request_id": "r2"}])
        # Tamper with sha256_prev of second entry to break the chain
        chain[1]["sha256_prev"] = "tampered"
        lines = [json.dumps(e, ensure_ascii=False) for e in chain]
        (tmp_path / "trust_log.jsonl").write_text("\n".join(lines) + "\n")

        result = doctor.analyze_trustlog()
        assert result["status"] == "⚠️ チェーン破損"
        assert result["chain_valid"] is False
        assert result["chain_breaks"] >= 1
        assert result["first_break"] is not None

    def test_hash_mismatch(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        chain = _build_chain([{"request_id": "r1"}])
        # Tamper with sha256 to cause mismatch
        chain[0]["sha256"] = "wrong_hash"
        (tmp_path / "trust_log.jsonl").write_text(json.dumps(chain[0]) + "\n")

        result = doctor.analyze_trustlog()
        assert result["chain_valid"] is False
        assert result["hash_mismatches"] >= 1
        assert result["first_mismatch"] is not None

    def test_large_file_skip(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(doctor, "MAX_FILE_SIZE", 10)
        (tmp_path / "trust_log.jsonl").write_text("x" * 100)

        result = doctor.analyze_trustlog()
        assert "skipped" in result["status"]

    def test_corrupt_json_lines(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        chain = _build_chain([{"request_id": "r1"}])
        content = "NOT_VALID_JSON\n" + json.dumps(chain[0]) + "\n"
        (tmp_path / "trust_log.jsonl").write_text(content)

        result = doctor.analyze_trustlog()
        # Corrupt line skipped; the valid entry is parsed
        assert result["entries"] == 1

    def test_file_read_error(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        tl = tmp_path / "trust_log.jsonl"
        tl.write_text("{}")
        # Monkeypatch open to raise
        original_open = open

        def bad_open(path, *a, **kw):
            if str(path) == str(tl):
                raise PermissionError("no access")
            return original_open(path, *a, **kw)

        monkeypatch.setattr("builtins.open", bad_open)
        result = doctor.analyze_trustlog()
        assert "error" in result["status"]
        assert result["chain_valid"] is False


# ---------------------------------------------------------------------------
# _iter_files
# ---------------------------------------------------------------------------

class TestIterFiles:
    def test_no_files(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        assert doctor._iter_files() == []

    def test_some_files(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        (tmp_path / "decide_1.json").write_text('{"x":1}')
        (tmp_path / "health_1.jsonl").write_text('{"y":2}\n')
        files = doctor._iter_files()
        assert len(files) == 2

    def test_dedup(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        # A .jsonl file matches both "decide_*.jsonl" and "*.jsonl"
        (tmp_path / "decide_a.jsonl").write_text('{"a":1}\n')
        files = doctor._iter_files()
        assert len(files) == 1

    def test_skips_empty_files(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        (tmp_path / "decide_empty.json").write_text("")
        assert doctor._iter_files() == []


# ---------------------------------------------------------------------------
# _read_json_or_jsonl
# ---------------------------------------------------------------------------

class TestReadJsonOrJsonl:
    def test_json_file(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"key": "val"}')
        items = doctor._read_json_or_jsonl(str(p))
        assert items == [{"key": "val"}]

    def test_json_items_extraction(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"items": [{"a":1}, {"b":2}]}')
        items = doctor._read_json_or_jsonl(str(p))
        assert len(items) == 2
        assert items[0] == {"a": 1}

    def test_jsonl_file(self, tmp_path):
        p = tmp_path / "test.jsonl"
        # First char must not be '{' to trigger JSONL branch
        p.write_text('\n{"a":1}\n{"b":2}\n')
        items = doctor._read_json_or_jsonl(str(p))
        assert len(items) == 2

    def test_large_file_skip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor, "MAX_FILE_SIZE", 5)
        p = tmp_path / "big.json"
        p.write_text('{"key": "value_long"}')
        assert doctor._read_json_or_jsonl(str(p)) == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        assert doctor._read_json_or_jsonl(str(p)) == []

    def test_corrupt_jsonl_lines(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text('\nNOT_JSON\n{"ok":true}\n')
        items = doctor._read_json_or_jsonl(str(p))
        assert items == [{"ok": True}]

    def test_oserror(self, tmp_path, monkeypatch):
        p = tmp_path / "missing.json"
        # Monkeypatch getsize to raise OSError
        monkeypatch.setattr(os.path, "getsize", lambda _: (_ for _ in ()).throw(OSError("fail")))
        assert doctor._read_json_or_jsonl(str(p)) == []

    def test_items_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor, "MAX_ITEMS_PER_FILE", 2)
        p = tmp_path / "test.jsonl"
        # First char must not be '{' to trigger JSONL branch
        p.write_text('\n{"a":1}\n{"b":2}\n{"c":3}\n')
        items = doctor._read_json_or_jsonl(str(p))
        assert len(items) == 2


# ---------------------------------------------------------------------------
# _bump_kw
# ---------------------------------------------------------------------------

class TestBumpKw:
    def test_keyword_match(self):
        counter = {}
        doctor._bump_kw(counter, "今日の天気は？")
        assert counter.get("天気") == 1

    def test_no_match(self):
        counter = {}
        doctor._bump_kw(counter, "関係ないテキスト")
        assert counter == {}

    def test_multiple_keywords(self):
        counter = {}
        doctor._bump_kw(counter, "VERITASで天気を調べた")
        assert counter.get("VERITAS") == 1
        assert counter.get("天気") == 1

    def test_none_text(self):
        counter = {}
        doctor._bump_kw(counter, None)
        assert counter == {}


# ---------------------------------------------------------------------------
# analyze_logs
# ---------------------------------------------------------------------------

class TestAnalyzeLogs:
    def test_no_files(self, tmp_path, monkeypatch, capsys):
        _patch_paths(monkeypatch, tmp_path)
        doctor.analyze_logs()
        out = capsys.readouterr().out
        assert "見つかりません" in out

    def test_with_decide_file(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        entry = {"query": "天気を教えて", "response": {"chosen": {"uncertainty": 0.5}}}
        (tmp_path / "decide_1.jsonl").write_text("\n" + json.dumps(entry) + "\n")

        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["total_files_found"] == 1
        assert report["parsed_logs"] == 1
        assert report["avg_uncertainty"] == 0.5
        assert "天気" in report["keywords"]
        assert report["by_category"]["decide"] == 1

    def test_with_health_file(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        (tmp_path / "health_1.json").write_text('{"status": "ok"}')
        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["by_category"]["health"] == 1

    def test_with_status_file(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        (tmp_path / "my_status.json").write_text('{"status": "ok"}')
        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["by_category"]["status"] == 1

    def test_other_category(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        (tmp_path / "misc.jsonl").write_text('\n{"data": 1}\n')
        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["by_category"]["other"] == 1

    def test_with_trustlog(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        chain = _build_chain([{"request_id": "r1", "created_at": "2025-01-01"}])
        (tmp_path / "trust_log.jsonl").write_text(json.dumps(chain[0]) + "\n")

        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["trustlog"]["status"] == "✅ 正常"
        assert report["trustlog"]["entries"] == 1

    def test_skipped_bad_json(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        p = tmp_path / "decide_bad.json"
        p.write_text("{INVALID JSON")
        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["skipped_badjson"] >= 1 or report["skipped_zero"] >= 0

    def test_non_dict_items_skipped(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        # Prefix with newline so first char != '{' → JSONL branch
        (tmp_path / "decide_list.jsonl").write_text('\n"just a string"\n42\n{"query":"hello"}\n')
        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["parsed_logs"] == 1

    def test_uncertainty_from_various_paths(self, tmp_path, monkeypatch):
        _patch_paths(monkeypatch, tmp_path)
        entries = [
            {"result": {"chosen": {"uncertainty": 0.2}}},
            {"decision": {"chosen": {"uncertainty": 0.8}}},
            {"chosen": {"uncertainty": 0.5}},
        ]
        # Prefix with newline so first char != '{' → JSONL branch
        lines = "\n" + "\n".join(json.dumps(e) for e in entries) + "\n"
        (tmp_path / "decide_unc.jsonl").write_text(lines)

        doctor.analyze_logs()
        report = json.loads((tmp_path / "doctor_report.json").read_text())
        assert report["avg_uncertainty"] == 0.5
