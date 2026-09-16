from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.audit.evidence_bundle import (
    _load_witness_entries as load_bundle_witness_entries,
)
from veritas_os.audit.evidence_bundle import generate_evidence_bundle
from veritas_os.cli.verify_trustlog import (
    _load_witness_entries as load_cli_witness_entries,
)
from veritas_os.cli.verify_trustlog import main as verify_trustlog_main


def _write_jsonl(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_cli_loader_rejects_malformed_trailing_record(tmp_path: Path) -> None:
    ledger = _write_jsonl(tmp_path / "witness.jsonl", "{}", '{"broken":')

    with pytest.raises(ValueError, match=r"line 2: invalid JSON"):
        load_cli_witness_entries(ledger)


def test_cli_loader_rejects_malformed_record_between_valid_entries(tmp_path: Path) -> None:
    ledger = _write_jsonl(tmp_path / "witness.jsonl", "{}", "not-json", "{}")

    with pytest.raises(ValueError, match=r"line 2: invalid JSON"):
        load_cli_witness_entries(ledger)


@pytest.mark.parametrize(
    "loader",
    [load_cli_witness_entries, load_bundle_witness_entries],
)
def test_witness_loaders_reject_non_object_json(loader, tmp_path: Path) -> None:
    ledger = _write_jsonl(tmp_path / "witness.jsonl", "[]")

    with pytest.raises(ValueError, match=r"line 1: expected JSON object"):
        loader(ledger)


def test_cli_returns_non_success_for_malformed_witness(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger = _write_jsonl(tmp_path / "witness.jsonl", "{}", '{"broken":')

    exit_code = verify_trustlog_main(
        ["--witness-ledger", str(ledger), "--json"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code != 0
    assert payload["ok"] is False
    assert "line 2" in payload["error"]


def test_evidence_bundle_aborts_before_packaging_malformed_witness(
    tmp_path: Path,
) -> None:
    ledger = _write_jsonl(tmp_path / "witness.jsonl", "{}", '{"broken":')
    output_dir = tmp_path / "bundles"

    with pytest.raises(ValueError, match=r"line 2: invalid JSON"):
        generate_evidence_bundle(
            bundle_type="decision",
            witness_ledger_path=ledger,
            output_dir=output_dir,
        )

    assert not output_dir.exists()
