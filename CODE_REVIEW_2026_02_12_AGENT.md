# CODE REVIEW 2026-02-12 (Agent)

## Scope
- Repository-wide lightweight review (`veritas_os`, `frontend`, `packages`) excluding vendored `node_modules`.
- Static grep-based security scan + Python lint + Python test run.

## Commands executed
1. `rg --files | head -n 200`
2. `rg -n "(eval\(|exec\(|subprocess\.|pickle\.loads|yaml\.load\(|os\.system\(|requests\.(get|post)\(|http://)" veritas_os frontend packages --glob '!**/node_modules/**'`
3. `python -m pytest -q -x`
4. `ruff check veritas_os`

## Summary of findings

### 1) Test environment inconsistency (High)
- `python -m pytest -q -x` failed with:
  - `async def functions are not natively supported`
  - `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`
- Impact:
  - Full CI confidence is reduced because async integration tests are not runnable in the default test environment.
  - Regressions in async paths may be missed.
- Recommendation:
  - Add and pin `pytest-asyncio` (or unify on `pytest-anyio`) in test dependencies.
  - Add explicit pytest marker configuration in `pyproject.toml`.

### 2) Transport security defaults are HTTP in multiple entry points (Medium)
- Several runtime defaults rely on `http://localhost` / `http://127.0.0.1`.
- Impact:
  - Local-only defaults are acceptable for development, but become risky if copied into shared/staging deployments.
- Recommendation:
  - Document stronger production defaults (`https://` + explicit host allowlist).
  - Add startup warnings when non-loopback HTTP endpoints are configured.

### 3) Outbound request surfaces present; retry/error hygiene is mostly good (Info)
- `veritas_os/tools/web_search.py` and `veritas_os/tools/github_adapter.py` have retry and bounded backoff logic.
- Good points:
  - Timeout usage and retry bounds are present.
  - Error message sanitization exists in `github_adapter`.
- Recommendation:
  - Consider optional egress/domain allowlist enforcement for stricter production hardening.

## Overall assessment
- Codebase health appears generally solid from lint and broad test execution progress.
- Most urgent actionable issue is async test plugin/config alignment.
