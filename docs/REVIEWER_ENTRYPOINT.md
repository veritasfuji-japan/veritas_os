# VERITAS OS Reviewer Entry Point

## Purpose

This document is the fastest entry point for external reviewers, enterprise evaluators, investors, and technical reviewers who want to understand VERITAS OS without reading the entire repository first.

It summarizes what to review, what is implemented, what is foundation-only, which proof packs exist, how to validate key claims, and what is intentionally not enabled.

## 30-minute review path

1. `README.md` — product overview and implemented scope boundary.
2. `docs/REVIEWER_ENTRYPOINT.md` — this repository-level reviewer guide.
3. `docs/governance/observe_mode_proof_pack.md` — Observe Mode evidence index.
4. `docs/ui/README_UI.md` — Mission Control and governance UI context.
5. `/dev/mission-fixture` — local/dev-only fixture viewer route for read-only inspection.
6. `bash scripts/validate_governance_observation_fixture.sh` — focused validation command for fixture integrity and rendering contract checks.

## What VERITAS OS is

VERITAS OS is an auditable decision operating system for LLM agents. It focuses on making AI decisions reviewable, traceable, reproducible, and governable through structured evidence, policy checks, decision artifacts, Mission Control visibility, and validation workflows.

It is a governance/control plane for decision and bind boundaries before real-world effect. It is not a claim that every effect path is fully production-complete today.

## Current implemented evidence areas

| Area | Where to look | What to verify |
|---|---|---|
| Decision / governance pipeline | `README.md`, `docs/INDEX.md` | Decision artifacts, governance pipeline concepts, evidence-oriented execution, fail-closed posture language. |
| Mission Control | `docs/ui/README_UI.md`, `frontend/components/mission-page.tsx`, `frontend/app/dev/mission-fixture/page.tsx` | Read-only operator visibility, governance artifact rendering, dev-only fixture viewer behavior. |
| Observe Mode foundation | `docs/governance/observe_mode_proof_pack.md`, `docs/governance/observe_mode.md` | Semantics, dry-run evaluator, CLI checker, dev-only snapshot generator, Mission Control read-only display, production fail-closed unchanged, runtime not enabled. |
| Fixture and validation integrity | `scripts/validate_governance_observation_fixture.sh`, `veritas_os/tests/test_governance_observation_fixture_drift.py`, `frontend/app/dev/mission-fixture/page.test.tsx` | Root/frontend fixture parity, CLI checker validity, Mission Control rendering tests for the fixture path. |
| Quality / validation commands | `README.md`, `scripts/check_governance_observation.py`, `scripts/generate_observe_mode_demo_snapshot.py` | Reproducible local checks, focused validation commands, proof-pack validation paths. |

## Production-ready vs foundation-only

### Implemented / reviewable

- Mission Control read-only governance artifact rendering.
- `governance_observation` schema/type foundation and documentation.
- Observe Mode dry-run validation tooling (evaluator + CLI checker).
- Dev-only fixture viewer with production disabled state.
- Fixture drift detection and focused validation scripts.
- Observe Mode demo snapshot generation for local/dev inspection.

### Foundation-only / not runtime-enabled

- Observe Mode runtime behavior.
- Production observe execution.
- Live backend emission of `governance_observation`.
- User-uploaded JSON loader for Mission Control.
- Automatic policy generation.
- Governance palette marketplace.
- Any production bypass path.

## Recommended validation commands

```bash
bash scripts/validate_reviewer_entrypoint.sh
bash scripts/validate_governance_observation_fixture.sh
python scripts/check_governance_observation.py fixtures/governance_observation_live_snapshot.json
python scripts/generate_observe_mode_demo_snapshot.py --out /tmp/observe_snapshot.json
python scripts/check_governance_observation.py /tmp/observe_snapshot.json
pnpm --filter frontend test app/dev/mission-fixture/page.test.tsx
```

The reviewer entrypoint validation script prints a summary block that can be pasted into `docs/reviewer_validation_report_template.md`.

Optional broader checks (already used in repository docs):

```bash
bash scripts/demo_mission_audit_workflow.sh
pnpm -r test
```

## Demo / inspection surfaces

### `/dev/mission-fixture`

- Local/dev/test oriented route.
- Production environment renders a disabled state.
- No backend API calls.
- No runtime Observe Mode activation.
- Static fixture only.
- Useful for reviewing Mission Control rendering contract.

### Observe Mode generated snapshot

```bash
python scripts/generate_observe_mode_demo_snapshot.py --out /tmp/observe_snapshot.json
python scripts/check_governance_observation.py /tmp/observe_snapshot.json
```

This is a dev/test evidence path. It is not production runtime evidence.

## Safety boundaries

- Production remains fail-closed.
- Observe Mode runtime is not enabled.
- No production bypass exists.
- No backend mutation endpoint is added by the Observe Mode foundation.
- Mission Control observation display is read-only.
- `/dev/mission-fixture` is disabled in production environment.
- Proof packs document evidence; they do not replace future runtime safety validation.

## Reviewer checklist

- [ ] Read `README.md` overview.
- [ ] Read `docs/governance/observe_mode_proof_pack.md`.
- [ ] Run `bash scripts/validate_reviewer_entrypoint.sh` (lightweight link + evidence smoke validation).
- [ ] Run focused validation script.
- [ ] Generate and check demo snapshot.
- [ ] Review `/dev/mission-fixture` locally.
- [ ] Confirm production disabled-state behavior.
- [ ] Confirm runtime non-goals.
- [ ] Confirm production fail-closed boundary.
- [ ] Identify foundation-only areas.
- [ ] Record unresolved questions.
- [ ] Record findings using `docs/reviewer_validation_report_template.md`.

## Open questions / limitations

- Some systems are foundation-only and not runtime-enabled.
- External security review is still needed before production claims beyond current scope.
- Production deployment posture should be evaluated separately per environment.
- Observe Mode runtime is not implemented.
- Live backend emission of `governance_observation` is not implemented.
- Demo routes are not substitutes for production runtime tests.
