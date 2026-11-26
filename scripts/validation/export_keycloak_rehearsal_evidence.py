"""Assemble the two successful Keycloak crash-rehearsal cases into CI evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

_SCENARIOS = {
    "kill-before-post": (0, "EFFECT_UNKNOWN"),
    "kill-after-lost-response": (1, "CONFIRMED_EFFECT"),
}
_HASH_FIELDS = (
    "effect_record_hash", "confirmation_hash", "receipt_bundle_hash",
    "bind_receipt_hash", "outcome_hash",
)
_TEST_COMMAND = "python -m pytest -q veritas_os/tests/test_keycloak_bind_role_rehearsal.py --tb=short"


def _read_scenario(directory: Path, name: str) -> dict:
    data = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    writes, state = _SCENARIOS[name]
    required = {
        "scenario": name,
        "provider_grant_events": writes,
        "recovery_post_requests": 0,
        "blocked_reservations": 2,
        "effect_state": state,
    }
    if not isinstance(data, dict) or data.keys() != required.keys() | set(_HASH_FIELDS):
        raise ValueError(f"{name}: unexpected evidence fields")
    if any(type(data[key]) is not type(value) or data[key] != value for key, value in required.items()):
        raise ValueError(f"{name}: outcome differs from the accepted rehearsal")
    for field in _HASH_FIELDS:
        value = data[field]
        if field == "effect_record_hash" or writes:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{name}: invalid {field}")
        elif value is not None:
            raise ValueError(f"{name}: unexpected {field} for an unresolved attempt")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--keycloak-image", required=True)
    parser.add_argument("--keycloak-image-id", required=True)
    parser.add_argument("--keycloak-repo-digest", required=True)
    parser.add_argument("--postgres-repo-digest", required=True)
    parser.add_argument("--postgres-version", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.tested_sha):
        parser.error("invalid tested SHA")
    if not re.fullmatch(r"quay\.io/keycloak/keycloak:[A-Za-z0-9_.-]+", args.keycloak_image):
        parser.error("invalid Keycloak image reference")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.keycloak_image_id):
        parser.error("invalid Keycloak image ID")
    if not re.fullmatch(r"quay\.io/keycloak/keycloak@sha256:[0-9a-f]{64}", args.keycloak_repo_digest):
        parser.error("invalid Keycloak repository digest")
    if not re.fullmatch(r"docker\.io/library/postgres@sha256:[0-9a-f]{64}", args.postgres_repo_digest):
        parser.error("invalid PostgreSQL repository digest")
    if not re.fullmatch(r"[0-9][A-Za-z0-9 .()+~_-]{0,127}", args.postgres_version):
        parser.error("invalid PostgreSQL server version")
    try:
        scenarios = [_read_scenario(args.scenario_dir, name) for name in _SCENARIOS]
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    report = {
        "format_version": "veritas-keycloak-crash-rehearsal/v1",
        "scope": "DISPOSABLE_KEYCLOAK_AND_POSTGRESQL",
        "tested_sha": args.tested_sha,
        "keycloak_image": args.keycloak_image,
        "keycloak_image_id": args.keycloak_image_id,
        "keycloak_repo_digest": args.keycloak_repo_digest,
        "postgres_repo_digest": args.postgres_repo_digest,
        "postgres_server_version": args.postgres_version,
        "test_command": _TEST_COMMAND,
        "workflow_file": ".github/workflows/keycloak-bind-role-rehearsal.yml",
        "scenarios": scenarios,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
