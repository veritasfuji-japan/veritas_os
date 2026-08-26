# Real Decision-to-Effect E2E — Stop Report

## Status

The controlled real Decision-to-Effect E2E proof is **stopped** at base commit
`e039496cefad9793f342f261940e4009806e5859` (merge commit for PR #2142).
No passing `report.json` has been produced.

## Missing production prerequisite

The reconciliation boundary exposes only the
`ReconciliationEvidenceVerifier` protocol. The repository has no reusable,
non-test implementation that independently observes and authenticates an
external acknowledgement before producing `VerifiedReconciliationEvidence`.

`reconcile_effect_unknown(...)` accepts a verifier implementing that protocol,
but it cannot itself establish that:

- the acknowledgement came from the authorization-bound TLS endpoint;
- the acknowledgement digest equals `external_ack_digest`;
- the observation digest is derived from the independently retrieved response;
- the external operation reference in the response matches the evidence; or
- a deployment-controlled verifier policy approved the observation source.

The existing controlled TLS runner fills this gap with the private
`_HttpsReconciliationVerifier`. That runner-local implementation directly
constructs `VerifiedReconciliationEvidence`; it is not a production verifier
primitive and does not validate the evidence's acknowledgement or observation
digests against the retrieved acknowledgement. Unit tests similarly use a
private `_Verifier` that returns a verified object without external
observation.

Promoting either private implementation into the requested E2E would violate
the requirements prohibiting test-only reconciliation trust and fake or
mismatched acknowledgement acceptance.

## Smallest prerequisite PR

Add one production reconciliation verifier, with focused fail-closed tests,
that:

1. accepts deployment-controlled HTTPS endpoint trust and verifier-policy
   configuration;
2. performs certificate-validated, independent acknowledgement retrieval;
3. canonicalizes the retrieved acknowledgement and verifies
   `external_ack_digest` and `observation_digest`;
4. binds operation, authorization, consumption, external reference, source,
   and observation time;
5. returns `VerifiedReconciliationEvidence` only after every binding passes;
6. rejects endpoint substitution, malformed responses, mismatched digests,
   mismatched operation references, and unapproved verifier policy; and
7. never accepts bearer material through an artifact or emits it in evidence.

After that prerequisite merges, the Decision-to-Effect composition can use
the production verifier through `reconcile_effect_unknown(...)` and can
legitimately derive `reconciliation_evidence_verified`,
`terminal_effect_confirmed`, and the final E2E conjunction.

## Security warning

Claiming `CONFIRMED_EFFECT` with the current runner-local verifier would allow
an acknowledgement/evidence digest mismatch to cross the reconciliation trust
boundary. The final E2E claim must remain false until the missing verifier is
implemented and independently tested.
