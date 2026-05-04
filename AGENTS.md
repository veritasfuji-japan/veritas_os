# VERITAS OS — Codex Agent Instructions

## Purpose

Codex is the primary implementation assistant for focused PRs in VERITAS OS.

This file defines how Codex should operate inside an auditable AI-assisted development workflow. It does not replace `CLAUDE.md`, `.github/copilot-instructions.md`, CI, or human maintainer approval.

## Authority Model

- AI reviews are advisory signals.
- GitHub Actions / CI are objective checks.
- Human maintainer approval is the final commit boundary.
- Codex must not push directly to `main`.
- Codex must not merge PRs.
- Codex must not approve security-sensitive, governance-sensitive, release-sensitive, or public-claim changes on its own.

## Scope Rules

- Prefer 1 PR = 1 purpose.
- Prefer small, reviewable diffs.
- Do not mix runtime changes, docs changes, and public positioning changes unless explicitly requested.
- If scope is unclear, reduce the change size instead of expanding it.
- Do not perform broad refactors unless explicitly requested.

## High-Risk Areas Requiring Human Approval

Human approval is required for changes touching:

- bind/admissibility logic
- governance policy behavior
- release gates
- secrets or credential handling
- TrustLog persistence or encryption behavior
- FUJI Gate fail-closed behavior
- public claims in README, docs, website, or social posts
- private user/customer data handling

## Priority Order

1. CI/test failures
2. Security or data exposure
3. Runtime behavior mismatch
4. Public documentation mismatch
5. Missing tests for code changes
6. Refactor or style suggestions

## External AI Review Safety

External/free-tier AI tools may be used only with non-sensitive excerpts.

Do not paste:

- secrets
- credentials
- API keys
- `.env` content
- private customer data
- unpublished internal strategy
- non-public security details

## References

- `CLAUDE.md` — project architecture, safety rules, testing, and quality gates
- `.github/copilot-instructions.md` — GitHub Copilot coding instructions
- `docs/en/development/ai-assisted-development.md` — canonical AI-assisted development guide
- `docs/ja/development/ai-assisted-development.md` — Japanese explanatory guide
