# Integrated Security Closure Regression v1

## Purpose

This gate executes the regression coverage for security findings F-01 through
F-08 as one required CI unit. It prevents an individually fixed boundary from
silently regressing after the policy, identity, replay, Trust feedback, or WAT
surfaces are composed on `main`.

The machine-readable source of truth is
`security/integrated_security_closure_v1.json`. The Security Gates workflow
runs `scripts/security/run_integrated_security_closure.py` on pull requests and
on pushes to `main`.

## Covered boundaries

| Finding | Required boundary |
| --- | --- |
| F-01 | Request values cannot disable server-mandated policy enforcement or select the runtime bundle. |
| F-02 | The signed manifest must bind the exact canonical policy bytes evaluated at runtime. |
| F-03 | Ed25519 verification cannot downgrade when trusted key material is missing. |
| F-04 | Authenticated principal identity owns decision-time memory retrieval. |
| F-05 | Caller metadata cannot redirect memory writes into another principal namespace. |
| F-06 | Public replay cannot enable external APIs. |
| F-07 | TrustLog read permission cannot write feedback, and writes use the authenticated principal. |
| F-08 | WAT validation cannot create issuance or revocation state transitions. |

The same run also preserves the native-v2 single-use consumption contract,
sandbox bind execution safety, and the frozen controlled Decision-to-Effect
proof boundary.

## Evidence and failure semantics

The gate succeeds only when every manifest target passes in one pytest process.
A missing target, incomplete F-01 through F-08 mapping, duplicate target, or
invalid manifest fails closed before tests run. CI failure blocks the security
closure claim until the regression is repaired or the manifest is deliberately
reviewed and updated.

## Explicit non-claims

Passing this gate does not establish production readiness, security
certification, resolution of all dependency advisories, use of real customer
credentials or endpoints, independent production infrastructure, or a
production Decision-to-Effect E2E proof. The existing controlled proof remains
bounded by its Architecture Freeze documentation.
