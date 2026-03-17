from pathlib import Path

from veritas_os.api.log_path_resolver import (
    effective_log_paths,
    effective_shadow_dir,
)


def test_effective_log_paths_follows_patched_log_dir(tmp_path: Path) -> None:
    """When LOG_DIR changes, default JSON/JSONL filenames follow the new dir."""
    log_dir = tmp_path / "logs"
    default_log_dir = Path("/repo/logs")

    _, log_json, log_jsonl = effective_log_paths(
        log_dir=log_dir,
        log_json=default_log_dir / "trust_log.json",
        log_jsonl=default_log_dir / "trust_log.jsonl",
        default_log_dir=default_log_dir,
        default_log_json=default_log_dir / "trust_log.json",
        default_log_jsonl=default_log_dir / "trust_log.jsonl",
    )

    assert log_json == log_dir / "trust_log.json"
    assert log_jsonl == log_dir / "trust_log.jsonl"


def test_effective_log_paths_respects_explicit_overrides(tmp_path: Path) -> None:
    """Explicit LOG_JSON/LOG_JSONL overrides are preserved."""
    log_dir = tmp_path / "logs"
    explicit_json = tmp_path / "custom.json"
    explicit_jsonl = tmp_path / "custom.jsonl"
    default_log_dir = Path("/repo/logs")

    _, log_json, log_jsonl = effective_log_paths(
        log_dir=log_dir,
        log_json=explicit_json,
        log_jsonl=explicit_jsonl,
        default_log_dir=default_log_dir,
        default_log_json=default_log_dir / "trust_log.json",
        default_log_jsonl=default_log_dir / "trust_log.jsonl",
    )

    assert log_json == explicit_json
    assert log_jsonl == explicit_jsonl


def test_effective_shadow_dir_follows_patched_log_dir(tmp_path: Path) -> None:
    """Default shadow dir switches to <LOG_DIR>/DASH when LOG_DIR is patched."""
    log_dir = tmp_path / "logs"
    default_log_dir = Path("/repo/logs")
    default_shadow_dir = default_log_dir / "DASH"

    shadow_dir = effective_shadow_dir(
        shadow_dir=default_shadow_dir,
        log_dir=log_dir,
        default_shadow_dir=default_shadow_dir,
        default_log_dir=default_log_dir,
    )

    assert shadow_dir == log_dir / "DASH"


def test_effective_shadow_dir_respects_explicit_override(tmp_path: Path) -> None:
    """Explicit SHADOW_DIR override is respected."""
    log_dir = tmp_path / "logs"
    custom_shadow = tmp_path / "custom-shadow"

    shadow_dir = effective_shadow_dir(
        shadow_dir=custom_shadow,
        log_dir=log_dir,
        default_shadow_dir=Path("/repo/logs/DASH"),
        default_log_dir=Path("/repo/logs"),
    )

    assert shadow_dir == custom_shadow
