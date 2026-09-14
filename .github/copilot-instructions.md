# VERITAS OS — GitHub Copilot Instructions

Read `AGENTS.md` first. It is the shared authority, safety, scope, and
progressive-disclosure entrypoint for coding agents in this repository.

This file contains only GitHub Copilot-specific behavior. Do not duplicate
volatile repository inventories here. Resolve current dependency versions,
endpoint counts, pipeline stages, test counts, and architecture details from
current code, manifests, generated specifications, tests, and CI.

## Copilot Role

GitHub Copilot is primarily used for:

- GitHub-native PR review
- local coding assistance
- focused implementation suggestions
- small bug and test-gap detection
- concise explanations of changed code

Keep suggestions narrow and compatible with the existing architecture. Do not
turn a local fix into a broad refactor unless explicitly requested.

## Authority Rules

- Copilot suggestions and reviews are advisory.
- GitHub Actions / CI are objective checks.
- Human maintainer approval is the final commit boundary.
- Do not independently approve or merge security-sensitive,
  governance-sensitive, release-sensitive, credential, external-effect, or
  public-claim changes.
- Do not infer execution authority from model confidence or a passing local
  test.

## Progressive Disclosure

1. Read `AGENTS.md`.
2. Inspect the changed files and directly related tests.
3. Read only the task-specific contract/architecture sources routed by
   `AGENTS.md`.
4. Use executable CI and repository checks for current quality/security gates.
5. Expand scope only when the diff has a demonstrated cross-boundary impact.

If code, documentation, tests, or CI conflict, flag the mismatch. Do not resolve
it by silently choosing one source.

## Implementation Guardrails

- Preserve Planner / Kernel / FUJI / MemoryOS / Pipeline responsibility
  boundaries enforced by repository checks.
- Keep LLM calls behind `veritas_os/core/llm_client.py`.
- Preserve fail-closed behavior.
- Never bypass Authority, Policy, Human Approval, Bind, or current-recheck
  boundaries.
- Never treat external measurement or other evidence as Authority Evidence,
  Human Approval, BindAuthorization, or execution permission unless the
  explicit contract says so.
- Do not introduce `pickle`, `joblib`, unsafe deserialization, plaintext
  secrets, or plaintext TrustLog persistence.
- Use specific exception handling and repository-standard logging.
- Add or update focused tests for behavior changes.

## Schema and Config Contracts

A schema/config change must update all affected artifacts in the same PR,
including:

- schema/model code
- committed JSON/YAML sample or default
- roundtrip/drift tests
- relevant sync/check scripts
- operational documentation

For governance policy changes, follow the canonical files and guard named in
`AGENTS.md`.

## Review Priority

1. CI/test failures
2. security or data exposure
3. governance/execution-boundary violations
4. runtime behavior mismatch
5. evidence-integrity or replay/tamper weaknesses
6. public documentation mismatch
7. missing tests
8. refactor or style suggestions

## External Sandbox Exception

The independent sandbox event service may use its documented distinct,
expiring Bearer writer/reader tokens. This exception is limited to
`create_sandbox_event_service`. Do not mount it into the main VERITAS API or
change that API's X-API-Key authentication. Missing authentication
configuration must fail closed.

## Current Facts

Do not encode changing facts such as "N endpoints", "N pipeline stages", "N
tests", or pinned library versions in this instruction file. Read those facts
from their authoritative repository sources when a task actually needs them.
