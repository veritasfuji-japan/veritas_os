"""Regression guards for the supported TrustLog verifier CLI surface."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from veritas_os.scripts import verify_trust_log as cli


def test_removed_compatibility_helpers_are_not_exposed() -> None:
    """Script-local compatibility helpers stay removed after consolidation."""
    for name in ("verify_entries", "compute_hash", "iter_entries"):
        assert not hasattr(cli, name)


def test_main_delegates_to_unified_verify_trustlogs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The supported CLI must continue to use the unified verifier path."""
    full_log = tmp_path / "trust_log.jsonl"
    witness_log = tmp_path / "trustlog.jsonl"
    witness_entries = [{"request_id": "w-1"}]
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: SimpleNamespace(
            full_log=full_log,
            witness_log=witness_log,
            max_entries=17,
            json=False,
        ),
    )
    monkeypatch.setattr(
        cli,
        "_read_all_entries",
        lambda path: witness_entries if path == witness_log else [],
    )

    def _verify_trustlogs(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(cli, "verify_trustlogs", _verify_trustlogs)
    monkeypatch.setattr(cli, "_print_human", lambda result: captured.update(printed=result))

    assert cli.main() == 0
    assert captured["full_log_path"] == full_log
    assert captured["witness_entries"] == witness_entries
    assert captured["verify_signature_fn"] is cli.verify_signature
    assert captured["max_entries"] == 17
    assert captured["printed"] == {"ok": True}
