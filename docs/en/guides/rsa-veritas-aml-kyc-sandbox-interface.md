# RSA ↔ VERITAS AML/KYC Sandbox Interface Contract

## Status and scope

This interface is a **sandbox fixture contract only**.

- It is intended for deterministic testing and review workflows.
- RSA remains an external upstream system.
- VERITAS consumes RSA-style status flags as upstream signals.
- VERITAS remains responsible for continuation admissibility, bind-boundary evaluation, final commit outcome, and audit logging.

## Compliance posture

This artifact is **not** production AML/KYC compliance logic.

This artifact is **not** legal advice and is **not** a regulatory certification.

## Current sandbox mapping

The receiver maps RSA upstream flags into VERITAS continuation behavior:

- `SAFE_PROCEED` → `CONTINUE_TO_BIND_BOUNDARY`
- `DENSITY_THROTTLED` → `CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED`
- `ALGORITHMIC_HUMILITY_ENGAGED` → `PAUSE_FOR_HUMAN_REVIEW`
- `DEFERRAL_ENGAGED` → `BLOCK_FINAL_COMMIT`

## Security note

Because this is sandbox-only behavior, production systems must not rely on this fixture as a sole AML/KYC gate. Production deployments require independently validated policy controls, authority evidence checks, and audited legal/regulatory review.
