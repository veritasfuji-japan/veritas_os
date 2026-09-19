"""Regression guards for TASK-017F dependency advisory closure."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "security" / "dependency_advisory_closure_v1.json"
PYPROJECT = ROOT / "pyproject.toml"
FULL_REQUIREMENTS = ROOT / "veritas_os" / "requirements.txt"
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "main.yml"
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security-gates.yml"

STARLETTE_ADVISORIES = {
    "PYSEC-2026-161",
    "PYSEC-2026-249",
    "PYSEC-2026-248",
    "PYSEC-2026-2281",
    "PYSEC-2026-2280",
}


def test_dependency_closure_manifest_and_pins_are_aligned() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    requirements = FULL_REQUIREMENTS.read_text(encoding="utf-8")

    env = manifest["closure_environment"]
    assert env["fastapi"] == "0.137.2"
    assert env["starlette_full_profile_pin"] == "1.3.1"
    assert env["sentence_transformers"] == "5.3.0"
    assert env["transformers"] == "5.10.0"

    for source in (pyproject, requirements):
        assert "fastapi==0.137.2" in source
        assert "transformers==5.10.0" in source
        assert "starlette==1.3.1" in source

    assert "fastapi==0.121.0" not in pyproject
    assert "transformers==5.5.0" not in pyproject
    assert "starlette==0.49.1" not in pyproject


def test_dependency_audits_have_no_temporary_starlette_waiver() -> None:
    for path in (MAIN_WORKFLOW, SECURITY_WORKFLOW):
        workflow = path.read_text(encoding="utf-8")
        assert "starlette_temp_ignores" not in workflow
        for advisory in STARLETTE_ADVISORIES:
            assert advisory not in workflow
        assert "Python full/optional dependency audit" in workflow
        assert "continue-on-error: true\n        run: pip-audit -r veritas_os/requirements.txt" not in workflow


def test_reported_vulnerable_runtime_surfaces_are_not_directly_used() -> None:
    """Keep the reviewed non-reachability assumptions explicit.

    Dependency upgrades are still required. This guard only prevents a future
    direct use of a previously reviewed vulnerable surface from being introduced
    without reopening the disposition.
    """

    forbidden = {
        "request.form(": "Starlette urlencoded form parser",
        "HTTPEndpoint": "Starlette arbitrary-method dispatch surface",
        "StaticFiles(": "Starlette Windows UNC StaticFiles surface",
        "request.url.hostname": "Starlette reconstructed-hostname surface",
        "save_pretrained(": "Transformers advisory write surface",
    }

    runtime_files = [
        path
        for path in (ROOT / "veritas_os").rglob("*.py")
        if "tests" not in path.parts
    ]

    hits: list[str] = []
    for path in runtime_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token, label in forbidden.items():
            if token in text:
                hits.append(f"{path.relative_to(ROOT)}: {label} ({token})")

    assert not hits, "Reviewed vulnerable surfaces became directly reachable:\n" + "\n".join(hits)


def test_bind_coverage_exporter_handles_fastapi_route_tree() -> None:
    from scripts.governance.export_bind_coverage_evidence import (
        generate_bind_coverage_evidence,
    )

    evidence = generate_bind_coverage_evidence(
        generated_at="1970-01-01T00:00:00+00:00"
    )

    assert evidence["total_runtime_routes"] >= 40
    assert evidence["classified_routes"] == evidence["total_runtime_routes"]
    assert evidence["status"] == "ok"
    assert "POST /v1/decide" in {
        f"{row['method']} {row['path']}" for row in evidence["routes"]
    }
