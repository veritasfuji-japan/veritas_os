# Release Gate Recovery Case Study

## Summary
VERITAS OS Release Gate blocked release promotion after detecting multiple release-blocking failures across governance persistence, runtime startup, and backend-specific test behavior. The first failures surfaced a PostgreSQL governance write-path defect and a Docker runtime startup defect. After those were remediated, the gate failed again on a test-isolation issue where a file-mode test was running under a PostgreSQL backend configuration. The gate returned to passing only after each blocking issue was corrected. This sequence shows an actual failure-to-green path, not a simulated exercise.

## Why this matters
This case shows the Release Gate is enforceable, not cosmetic. Release-blocking checks failed in CI and prevented release promotion until remediation. Docker runtime startup was validated at execution time, not only at image build time. PostgreSQL governance persistence behavior was also validated on the release path. The recovery also required explicit file-backend and PostgreSQL-backend test isolation. The final passing state indicates governance-ready release status was reached only after correction.

## Failure 1: PostgreSQL JSONB adaptation
- **Symptom:** Release Gate failed with `psycopg.ProgrammingError: cannot adapt type 'dict' using placeholder '%s'` during governance persistence writes.
- **Root cause:** Python `dict`/`list` payloads were sent to PostgreSQL JSONB columns without psycopg JSONB adaptation.
- **Fix:** JSONB-bound payloads were wrapped with `Jsonb(...)` in the governance PostgreSQL repository write path.
- **Governance significance:** Governance artifacts could not be reliably persisted to PostgreSQL until adaptation was corrected, so release promotion remained blocked.

## Failure 2: Docker runtime startup
- **Symptom:** Backend container startup failed with `exec: "uvicorn": executable file not found in $PATH`.
- **Root cause:** Dependencies were installed under `/app/deps`, but `/app/deps/bin` was not on `PATH`.
- **Fix:** `/app/deps/bin` was added to `PATH`, and backend startup was changed to `python -m uvicorn`.
- **Runtime significance:** The gate validated runnable startup behavior, not only artifact creation, and blocked promotion until runtime entrypoint execution was corrected.

## Failure 3: File/PostgreSQL test isolation
- **Symptom:** `veritas_os/tests/test_governance_repository.py::test_file_mode_behavior_unchanged_for_load_save` failed with `FileNotFoundError` on `tmp_path / "governance.json"`.
- **Root cause:** The Release Gate job intentionally ran with `VERITAS_GOVERNANCE_BACKEND=postgresql`, while the test asserted legacy file-mode behavior without forcing file backend.
- **Fix:** The test was isolated to file backend by explicitly setting `VERITAS_GOVERNANCE_BACKEND=file` and unsetting `VERITAS_DATABASE_URL` in test setup.
- **Test-governance significance:** Multi-backend repositories require explicit backend isolation in tests; otherwise, governance behavior can be validated against the wrong persistence mode.

## Final outcome
After remediating all three issues, Release Gate passed. This does not claim that all future releases are automatically safe. It shows the gate can detect concrete release risks, block release promotion, and validate remediation before a release is treated as governance-ready.

## What this demonstrates about VERITAS OS
- Governance checks are enforceable.
- Release readiness is evidence-driven.
- Backend persistence is part of the release contract.
- Runtime health is part of the release contract.
- Test isolation matters when multiple backends exist.
- A release is not considered governance-ready until blocking checks pass.
