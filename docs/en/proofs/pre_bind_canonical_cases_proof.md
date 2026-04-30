# Pre-bind participation / detection / preservation canonical proof cases

This proof document provides reproducible reviewer evidence for the canonical
pre-bind state combinations.

## Scope and non-goal

- Scope: pre-bind **participation detection** (`informative|participatory|decision_shaping`)
  and pre-bind **preservation** (`open|degrading|collapsed`) reproducibility.
- Non-goal: bind permission changes. These cases are not bind-time authorization.

## Canonical case matrix

| Case ID | Input signal profile | Expected participation state | Expected preservation state |
| --- | --- | --- | --- |
| `pre_bind_case_informative_open` | open/high/high/open | `informative` | `open` |
| `pre_bind_case_participatory_degrading` | narrowing/low/medium/fragile | `participatory` | `degrading` |
| `pre_bind_case_decision_shaping_collapsed` | closed/none/low/closed | `decision_shaping` | `collapsed` |

## Case A: pre_bind_case_informative_open

- Input signals
  - `interpretation_space_narrowing: open`
  - `counterfactual_availability: high`
  - `intervention_headroom: high`
  - `structural_openness: open`
- Expected pre-bind detection state: `informative`
- Expected preservation state: `open`
- Why this state:
  - Interpretation space is not narrowed.
  - Counterfactual exploration remains available.
  - Intervention remains meaningfully available.
  - Structural openness floor is preserved.
- Bind-time governance relation:
  - This is an upstream governability signal only.
  - Bind decision remains controlled by bind-time contracts.

## Case B: pre_bind_case_participatory_degrading

- Input signals
  - `interpretation_space_narrowing: narrowing`
  - `counterfactual_availability: low`
  - `intervention_headroom: medium`
  - `structural_openness: fragile`
- Expected pre-bind detection state: `participatory`
- Expected preservation state: `degrading`
- Why this state:
  - Decision formation influence is emerging.
  - Counterfactual space remains but is weakened.
  - Intervention remains possible, yet recovery difficulty increases.
- Bind-time governance relation:
  - Still pre-bind only; not bind permission.

## Case C: pre_bind_case_decision_shaping_collapsed

- Input signals
  - `interpretation_space_narrowing: closed`
  - `counterfactual_availability: none`
  - `intervention_headroom: low`
  - `structural_openness: closed`
- Expected pre-bind detection state: `decision_shaping`
- Expected preservation state: `collapsed`
- Why this state:
  - Interpretation/option space is materially constrained.
  - Counterfactual recovery is unavailable.
  - Meaningful intervention viability is no longer realistic.
- Bind-time governance relation:
  - This does not auto-grant or auto-deny bind.
  - Bind remains separate downstream governance.

## Repro artifacts

- Fixtures: `veritas_os/tests/fixtures/pre_bind/`
- Goldens: `veritas_os/tests/golden/pre_bind/`
- Canonical tests: `veritas_os/tests/test_pre_bind_canonical_golden.py`
- HTTP endpoint E2E parity tests for `/v1/decide`: `veritas_os/tests/test_pre_bind_http_e2e.py`
- Real pipeline `/v1/decide` reliability extension for canonical cases:
  `veritas_os/tests/test_decide_e2e_reliability.py` (`TestCanonicalPreBindRealPipelineRequestInputSeam`)
- Vocabulary consistency + rationale-linked assertions: `test_canonical_case_naming_and_vocabulary_consistency` and
  `test_canonical_pre_bind_signals_and_rationales_are_explanatory` in the same test module.


## Coverage split (golden vs HTTP E2E)

- Golden canonical tests protect detection/preservation semantics and rationale drift at evaluator-level snapshots.
- HTTP E2E tests protect `/v1/decide` endpoint wiring, response contract shape, additive optionality, and bind-field non-regression.
- Real pipeline reliability E2E protects the non-stubbed HTTP → route → pipeline → response assembly path for canonical
  cases (including additive field optionality and bind-family field presence).
- Migration note: canonical reliability deterministic control was moved from legacy raw-extras monkeypatch injection to the request-input seam (`context.pre_bind_participation_signal`) for the canonical main path.
- Deterministic control in that layer is intentionally limited to request input shaping:
  canonical `participation_signal` is passed via `/v1/decide` request
  `context.pre_bind_participation_signal`.
- Pipeline input normalization extracts that test-only context key, normalizes it as a canonical
  `participation_signal`, and places it into response extras before governance-layer evaluation.
- The test hook key is removed from runtime context after extraction to keep the seam isolated.
- Response-layer governance evaluation is still executed through the normal implementation
  (`pipeline_response.evaluate_governance_layers`) without monkeypatch replacement in canonical reliability tests.
- This boundary is more natural than patching `call_core_decide(...)->raw["extras"]`, while preserving deterministic
  stability and avoiding flaky behavior.
- Bind behavior is unchanged: pre-bind signals remain additive governance evidence only.
