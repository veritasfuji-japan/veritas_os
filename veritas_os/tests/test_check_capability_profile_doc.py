"""Tests for scripts.quality.check_capability_profile_doc."""

from __future__ import annotations

from scripts.quality import check_capability_profile_doc as checker


def test_collect_missing_tokens_reports_missing_required_markers() -> None:
    """Checker should list missing capability-profile markers."""
    missing = checker.collect_missing_tokens(
        "## 6.3 capability profile / strict mode 推奨\n"
    )

    assert "### production 推奨設定" in missing
    assert "VERITAS_CAP_FUJI_TRUST_LOG=1" in missing
    assert "VERITAS_AUTH_STORE_FAILURE_MODE=open" in missing
    assert "[CapabilityManifest]" in missing


def test_main_returns_success_for_current_runbook(capsys) -> None:
    """Repository runbook should satisfy the capability-profile doc check."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Capability profile runbook guidance passed checks." in output
