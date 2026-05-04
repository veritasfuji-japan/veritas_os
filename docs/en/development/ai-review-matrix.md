# AI Review Matrix

## Purpose

This matrix defines how different AI tools may be used during VERITAS OS development.

It supports the auditable AI-assisted development workflow defined in `docs/en/development/ai-assisted-development.md`.

AI reviews are advisory. GitHub Actions / CI are objective checks. Human maintainer approval is the final commit boundary.

## Role Matrix

| Tool | Primary role | Best used for | Not authority for |
|---|---|---|---|
| ChatGPT | Planning and strategic review | PR intent, scope, risk framing, market/developer/user value, public messaging review | merge approval, CI override, security/governance approval |
| Codex | Primary implementation | focused patches, tests, CI failure fixes, small docs updates | independent merge, security-sensitive approval, public-claim approval |
| Claude Code | Architecture and implementation review | architecture consistency, edge cases, terminology consistency, missing/weak tests, governance-sensitive review | CI override, final approval, autonomous refactor approval |
| GitHub Copilot | GitHub-native review and local coding assistance | small bug suggestions, code readability, local implementation assistance | final approval, governance/security approval |
| Gemini | External clarity review | documentation readability, product explanation, external reviewer perspective | merge blocker, confidential review |
| Grok | Adversarial review | unnecessary-complexity detection, market/message skepticism, overengineering detection | final architecture authority |
| Meta AI | Lightweight secondary review | terminology clarity, readability, second opinion | merge blocker, sensitive review |
| GitHub Actions | Objective verification | tests, quality gates, release gates, CodeQL, automation checks | product strategy or public messaging |
| Human maintainer | Final authority | final approval, merge decision, security/governance/release/public-claim approval | none |

## Feedback Classification

AI feedback should be classified as:

- `blocker`: must be addressed before merge
- `recommended`: should be addressed unless there is a clear reason not to
- `optional`: style, readability, alternative implementation, or non-critical suggestion

Only a human maintainer may decide whether advisory AI feedback becomes a merge blocker.

## Review Priority

1. CI/test failures
2. Security or data exposure
3. Runtime behavior mismatch
4. Public documentation mismatch
5. Missing tests for code changes
6. Refactor or style suggestions

## High-Risk Changes

The following changes require explicit human approval:

- bind/admissibility logic
- governance policy behavior
- release gates
- secrets or credential handling
- TrustLog persistence or encryption behavior
- FUJI Gate fail-closed behavior
- public claims in README, docs, website, or social posts
- private user/customer data handling

## External AI Review Safety

External/free-tier tools must receive only non-sensitive excerpts.

Do not paste secrets, credentials, API keys, `.env` content, private customer data, unpublished internal strategy, or non-public security details.
