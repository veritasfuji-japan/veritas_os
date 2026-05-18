# RSA ↔ VERITAS Static Fixture Matrix

## 1. Purpose

This document summarizes the static RSA-compatible fixture variants used in the V.I.K.I. ↔ VERITAS sandbox validation flow.

The goal is to show the deterministic mapping from upstream RSA-compatible status to VERITAS continuation decision, reason code, audit posture, and commit state.

## 2. Current baseline

The current merged baseline includes:

- RSA / V.I.K.I. / VERITAS terminology synchronization.
- Existing RSASandboxPayload receiver contract.
- Existing evaluate_rsa_sandbox_signal(payload) mapping.
- Existing E2E sandbox harness.
- Existing governance-backend-fast CI coverage.
- Existing ALGORITHMIC_HUMILITY_ENGAGED validation snapshot.
- Existing DENSITY_THROTTLED validation snapshot.
- Existing DEFERRAL_ENGAGED validation snapshot.
- Existing SAFE_PROCEED validation snapshot.

## 3. Terminology compatibility note

- RSA remains the theoretical framework and underlying rule set.
- V.I.K.I. is the operational producer of RSA-compatible upstream payloads.
- VERITAS is the downstream commit governance boundary.
- rsa_status remains unchanged for compatibility.
- RSASandboxPayload remains the VERITAS-side receiver contract name.
- upstream_signal_source = "RSA" is retained as a v1 compatibility fixture/source label.
- That compatibility label does not mean VERITAS consumes V.I.K.I. internal reasoning.
- VERITAS consumes only the emitted payload.

## 4. Static fixture matrix

| rsa_status | upstream meaning | VERITAS continuation_decision | reason_code | sandbox_commit_state | review posture |
| --- | --- | --- | --- | --- | --- |
| SAFE_PROCEED | Upstream signal indicates the workflow may continue toward normal bind-boundary evaluation. | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED | continue to normal sandbox bind-boundary evaluation |
| DENSITY_THROTTLED | Upstream output was modified for cognitive-density control. | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED | continue with upstream intervention logged |
| ALGORITHMIC_HUMILITY_ENGAGED | Required context or authority evidence is incomplete. | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED | pause for human review or additional evidence |
| DEFERRAL_ENGAGED | Critical upstream deferral condition reported before final commit. | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED | hard block final commit until review or remediation |

## 5. Escalation ladder

SAFE_PROCEED  
→ normal continuation

DENSITY_THROTTLED  
→ soft intervention logged

ALGORITHMIC_HUMILITY_ENGAGED  
→ pause for human review

DEFERRAL_ENGAGED  
→ block final commit

This ladder gives reviewers a compact view of the sandbox governance behavior without connecting live V.I.K.I. middleware.

## 6. Snapshot relationship

This matrix is designed to be read alongside the existing snapshot pages:

- [RSA ↔ VERITAS E2E Sandbox Validation Snapshot](./rsa-veritas-e2e-sandbox-validation-snapshot.md) — includes the ALGORITHMIC_HUMILITY_ENGAGED E2E path.
- [SAFE_PROCEED validation snapshot](./rsa-veritas-safe-proceed-validation-snapshot.md)
- [RSA ↔ VERITAS DENSITY_THROTTLED Validation Snapshot](./rsa-veritas-density-throttled-validation-snapshot.md)
- [RSA ↔ VERITAS DEFERRAL_ENGAGED Validation Snapshot](./rsa-veritas-deferral-engaged-validation-snapshot.md)

## 7. What this validates

- All current static RSA-compatible statuses are summarized in one reviewable matrix.
- VERITAS has deterministic continuation decision mappings for the static fixture variants.
- The matrix shows the range from safe continuation to soft intervention, pause, and hard commit block.
- Existing compatibility labels and receiver contracts remain stable.
- The current sandbox validation flow remains reviewable without connecting live V.I.K.I. logic.

## 8. What this does not validate

- It does not connect live V.I.K.I. middleware.
- It does not validate V.I.K.I. internal reasoning.
- It does not determine real-world compliance status.
- It does not implement production AML/KYC compliance.
- It does not provide regulatory approval.
- It does not provide third-party certification.
- It does not provide legal advice.
- It does not use real customer, financial, medical, KYC, or regulated data.
- It does not change production runtime governance.

## 9. Next sandbox step

The current static fixture variants are now covered by the matrix and snapshot documentation. SAFE_PROCEED, DENSITY_THROTTLED, and DEFERRAL_ENGAGED have dedicated per-variant snapshots, while ALGORITHMIC_HUMILITY_ENGAGED is covered by the broader E2E sandbox validation snapshot.

The next safe sandbox step is to add a lightweight reviewer index page linking the E2E sandbox validation snapshot, available per-variant snapshots, the static fixture matrix, the AML/KYC scenario map, and the E2E sandbox demo plan.

If strict one-page-per-status symmetry is required later, a dedicated ALGORITHMIC_HUMILITY_ENGAGED per-variant snapshot can be added in a follow-up documentation PR.

No live V.I.K.I. connection should be added before the reviewer index is documented and reviewed.
