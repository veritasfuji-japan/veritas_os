# Debate Safety Policy YAML Migration Plan (Phase 0/1)

## Status and scope

- Status: planning + non-runtime config skeleton only.
- Scope in this change:
  - Document current hardcoded Debate safety heuristics inventory.
  - Define phased migration to policy-as-data YAML.
  - Add a non-authoritative example YAML config skeleton.
- Out of scope in this change:
  - Any runtime behavior change.
  - Any enablement of YAML loading in the Debate runtime path.

## Current problem

The Debate stage currently contains hardcoded safety terms and regex patterns in
`veritas_os/core/debate.py` (for example, danger terms, dangerous intent,
actionable intent, instructional cues, refusal contexts, and risk-delta signals).
This makes safety behavior harder to:

- audit as policy,
- version and review as standalone artifacts,
- compare safely across revisions,
- validate deterministically before production use.

## Design goals

1. **Policy-as-data**
   - Represent Debate safety policy in structured YAML instead of only inline code constants.
2. **Versioned YAML**
   - Include explicit schema/version fields and policy identifiers.
3. **Deterministic loading**
   - No network fetches; load from local/approved artifact paths only.
4. **Validation before use**
   - Parse + schema validation must pass before policy is considered usable.
5. **Fail-closed on malformed production policy**
   - Production strict mode must not silently weaken enforcement.
6. **Snapshot-style tests for policy revisions**
   - Policy updates should be reviewable through explicit diffs and test fixtures.
7. **No silent weakening of safety behavior**
   - Migration must prove parity (or explicit intentional strengthening) before enforcement switch.

## Non-goals for this PR

- No runtime behavior change.
- No removal of existing hardcoded checks in `veritas_os/core/debate.py`.
- No automatic external policy fetch.

## Inventory of current hardcoded Debate safety signals (Phase 0)

Current hardcoded policy-like artifacts live in `veritas_os/core/debate.py`:

- `_DANGER_TERMS_JA`
- `_DANGER_PATTERNS_EN`
- `_BENIGN_CONTEXT_STRONG_TERMS`
- `_BENIGN_CONTEXT_WEAK_TERMS`
- `_DANGEROUS_INTENT_PATTERNS`
- `_ACTIONABLE_INTENT_PATTERNS`
- `_INSTRUCTIONAL_CUE_PATTERNS`
- `_RISK_NEGATION_TERMS`
- `_ASCII_RISK_NEGATION_BY_KEYWORD`
- `_JA_RISK_NEGATION_BY_KEYWORD`
- `_REFUSAL_CONTEXT_PATTERNS`
- `_RISK_KEYWORDS_WEIGHTED`
- `_REGULATORY_AMBIGUITY_PATTERNS`
- `_REGULATORY_AMBIGUITY_NEGATION_TERMS`

These constants are the baseline behavior to preserve while migrating.

## Phased migration plan

### Phase 0 — Inventory current hardcoded rules

- Freeze and document current constants/pattern groups.
- Add explicit traceability from docs to code locations.

### Phase 1 — Add YAML schema/skeleton and validation tests

- Add non-authoritative example YAML policy document.
- Add lightweight parse/shape tests for example policy artifact.
- Keep runtime disconnected from this YAML.

### Phase 2 — Shadow load + parity comparison

- Add optional shadow loader that reads YAML policy without enforcing it.
- Compare shadow policy evaluation with hardcoded evaluation in tests.
- Fail tests on unexpected drift.

### Phase 2.5 — Export hardcoded inventory + conservative parity visibility

- Export a review-facing hardcoded inventory metadata report from
  `veritas_os/policy/debate_safety_policy_loader.py`.
- Keep parity reporting conservative (`parity_unknown` is expected until full
  inventory alignment is intentionally addressed).
- Runtime Debate enforcement remains hardcoded and authoritative.
- YAML remains non-authoritative in this phase.
- Phase 3 is blocked until inventory parity gaps are intentionally resolved and
  documented.

### Phase 3 — Feature-flag YAML enforcement

- Gate YAML-based enforcement behind explicit capability/feature flag.
- Keep default behavior aligned with current hardcoded path until parity proof passes.

### Phase 4 — Retire duplicated hardcoded patterns after parity proof

- Remove duplicated hardcoded definitions only after:
  - parity report,
  - test coverage proving equivalence/safe strengthening,
  - human security review.

## Security posture and review notes

- This migration domain is security-sensitive.
- Policy loading and validation must remain fail-closed in strict production modes.
- No permissive fallback should silently reduce protections.
- Human approval is required before any enforcement-path switch.

## Cross references

- Debate risk mapping in decide response plan:
  `docs/architecture/decide-response-v2-plan.md`
- FUJI policy and fail-closed guidance:
  `docs/ja/guides/fuji-eu-enterprise-strict-usage.md`
- Responsibility boundaries:
  `docs/architecture/core_responsibility_boundaries.md`

## Phase 2 status update (shadow-only)

- A dedicated shadow loader is now available at
  `veritas_os/policy/debate_safety_policy_loader.py`.
- Loader behavior is intentionally non-authoritative:
  - loads YAML from an explicit local path only,
  - uses `yaml.safe_load`,
  - validates with `DebateSafetyPolicy.model_validate`,
  - raises explicit errors for malformed YAML or schema violations.
- Debate runtime enforcement remains hardcoded in `veritas_os/core/debate.py`.
- YAML policy is **not** the source of truth in Phase 2 and must not be used to
  switch enforcement behavior.
- Operator warning: Do **not** treat YAML policy as authoritative yet.
- Future production strict-mode requirement remains: malformed production policy
  must fail closed, but Phase 2 does not activate production enforcement from
  YAML.

## Phase 2.5 status update (inventory export only)

- Hardcoded Debate safety inventory metadata is now exportable for review/test
  visibility (category names and pattern counts).
- Parity report remains conservative by design and must not be interpreted as
  semantic equivalence proof.
- Runtime enforcement is still hardcoded in `veritas_os/core/debate.py`.
- YAML policy remains non-authoritative and does not drive runtime decisions.

## Phase 3 entry checklist (must pass before activation work)

- No missing hardcoded categories in parity inventory, or an explicit and
  reviewed migration decision documenting each remaining gap.
- Parity-focused tests pass in CI.
- Any feature flag for YAML enforcement defaults to off.
- Malformed policy fail-closed behavior is designed and test-covered.
- Policy diagnostics avoid raw PII/secrets output.
