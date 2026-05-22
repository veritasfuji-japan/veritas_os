# Debate Safety Policy Migration Mapping (Phase 2.6)

## Purpose

This document defines the **Phase 2.6/2.7 planning/mapping baseline** for migrating
hardcoded Debate safety categories into a future YAML policy model.

Machine-readable artifact: `docs/architecture/debate-safety-policy-migration-map.yaml`
(planning-only, non-authoritative).

It exists to prevent accidental behavior drift during Phase 3 planning:

- YAML remains **non-authoritative** in Phase 2.x.
- Hardcoded Debate behavior in `veritas_os/core/debate.py` remains the source of
  truth for runtime enforcement.
- No runtime enforcement switch is introduced by this mapping document.

## Current hardcoded inventory categories

The current hardcoded inventory exported by
`export_hardcoded_debate_safety_inventory()` includes the following categories:

1. `danger_terms_ja`
2. `danger_patterns_en`
3. `benign_context_strong_terms`
4. `benign_context_weak_terms`
5. `dangerous_intent_patterns`
6. `actionable_intent_patterns`
7. `instructional_cue_patterns`
8. `risk_negation_terms`
9. `ascii_risk_negation_by_keyword`
10. `ja_risk_negation_by_keyword`
11. `refusal_context_patterns`
12. `risk_keywords_weighted`
13. `regulatory_ambiguity_patterns`
14. `regulatory_ambiguity_negation_terms`

## Proposed YAML mapping table (planning only)

> Status vocabulary:
> - `direct`: expected one-to-one mapping
> - `split`: one hardcoded category likely split across multiple YAML categories
> - `merge`: multiple hardcoded categories likely merged into one YAML category
> - `derived`: YAML value derived from structured/weighted source, not copied verbatim
> - `TBD`: unresolved mapping design


> Note: three proposed YAML category names differ from their hardcoded
> counterparts. In all other cases the proposed YAML category name is
> identical to the hardcoded name.
>
> | Hardcoded name                  | Proposed YAML name               |
> |---|---|
> | ascii_risk_negation_by_keyword  | risk_negation_by_keyword_ascii   |
> | ja_risk_negation_by_keyword     | risk_negation_by_keyword_ja      |
> | risk_keywords_weighted          | risk_keyword_weights             |

| Hardcoded category | Proposed YAML category | Migration status | Notes / risks |
|---|---|---|---|
| `danger_terms_ja` | `danger_terms_ja` | `direct` | Low structural risk; semantic parity still requires regex/term review. |
| `danger_patterns_en` | `danger_patterns_en` | `direct` | Low structural risk; language-boundary edge cases still need validation. |
| `benign_context_strong_terms` | `benign_context_strong_terms` | `direct` | Context interaction risk if used without companion weak/context signals. |
| `benign_context_weak_terms` | `benign_context_weak_terms` | `direct` | Weak signals are calibration-sensitive; avoid accidental weighting drift. |
| `dangerous_intent_patterns` | `dangerous_intent_patterns` | `direct` | High safety sensitivity; must preserve strict intent matching behavior. |
| `actionable_intent_patterns` | `actionable_intent_patterns` | `direct` | Actionability semantics may be coupled to runtime scoring/decision flow. |
| `instructional_cue_patterns` | `instructional_cue_patterns` | `direct` | Cue patterns can be over-broad; parity review must include false-positive risk. |
| `risk_negation_terms` | `risk_negation_terms` | `direct` | Negation handling is brittle; do not migrate without targeted tests. |
| `ascii_risk_negation_by_keyword` | `risk_negation_by_keyword_ascii` | `derived` | Keyword-indexed structure may need canonical ordering/normalization rules. |
| `ja_risk_negation_by_keyword` | `risk_negation_by_keyword_ja` | `derived` | Locale-specific tokenization/normalization rules must be explicitly defined. |
| `refusal_context_patterns` | `refusal_context_patterns` | `direct` | Refusal heuristics can suppress risk; migration must verify no safety weakening. |
| `risk_keywords_weighted` | `risk_keyword_weights` | `derived` | Weighted map cannot be blindly converted to flat patterns without scoring design. |
| `regulatory_ambiguity_patterns` | `regulatory_ambiguity_patterns` | `direct` | Ambiguity logic interacts with policy interpretation; preserve conservative behavior. |
| `regulatory_ambiguity_negation_terms` | `regulatory_ambiguity_negation_terms` | `direct` | Negation + ambiguity coupling requires explicit precedence/ordering in Phase 3 design. |

## Categories that must not be blindly migrated

The following categories are structurally and semantically sensitive. They
require explicit design notes and dedicated tests before any enforcement-path
switch:

- Negation terms:
  - `risk_negation_terms`
  - `regulatory_ambiguity_negation_terms`
- Context terms:
  - `benign_context_strong_terms`
  - `benign_context_weak_terms`
  - `refusal_context_patterns`
- Weighted risk maps:
  - `risk_keywords_weighted`
- Ambiguity patterns:
  - `regulatory_ambiguity_patterns`

## Phase 3 entry criteria (gating)

Phase 3 remains blocked until all criteria below are satisfied:

1. No unexplained missing hardcoded categories.
2. Explicit mapping decision for every hardcoded category.
3. Tests that detect category inventory drift.
4. Feature flag default remains off.
5. Fail-closed behavior is designed for malformed production policy.
6. No remote policy fetch.
7. No runtime enforcement switch yet.
8. Machine-readable migration mapping artifact is present at
   docs/architecture/debate-safety-policy-migration-map.yaml, and a
   validator/test confirms that every key in _HARDCODED_CATEGORY_MAP
   has an explicit entry in that file.
9. The mapping validator is green in CI and human review explicitly approves
   the mapping before any Phase 3 enforcement-path switch is considered.

## Security and operations note

This migration area is safety-sensitive. Any mapping change that can alter
runtime behavior must be reviewed as a security-relevant change before
feature-flagged enforcement is considered.


## Phase 2.7 artifact status

The YAML mapping artifact is **planning-only** and **non-authoritative** in
Phase 2.7. Runtime enforcement remains hardcoded. Phase 3 remains blocked
until the mapping validator passes and human review approves the mapping.
