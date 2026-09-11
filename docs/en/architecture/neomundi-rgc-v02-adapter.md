# NeoMundi RGC v0.2 External Measurement Adapter

## Status

Provider-specific interoperability adapter layered on the provider-neutral `ExternalMeasurementEvidence` boundary introduced in PR #2225.

This adapter targets NeoMundi Measurement Interoperability Contract RGC JSON v0.2 only:

```text
identity.schema_version == "0.2.0"
```

RGC v0.1 remains a historical contract and is not silently interpreted under v0.2 semantics.

## Boundary

```text
Untrusted NeoMundi RGC v0.2 artifact
        ↓
VERITAS-controlled RGC structure / semantic checks
        ↓
canonical payload reconstruction
        ↓
SHA-256 payload verification
        ↓
Ed25519 / compact JWS verification
        ↓
consumer-controlled trusted JWKS binding
        ↓
ExternalMeasurementEvidence
        ↓
provider-neutral VERITAS trust / freshness / replay boundary
        ↓
independent VERITAS governance
```

The governing invariants are:

```text
Measurement != Authority
Advisory != Authorization
Within Bounds != ALLOW
Valid Signature != Trusted Provider
External Evidence != Governance Decision
```

The adapter never creates `AuthorityEvidence`, `HumanApproval`, `BindAuthorization`, an ALLOW/DENY decision, or execution permission.

## Canonical payload

The adapter independently reconstructs the same payload described by NeoMundi's public RGC v0.2 reference consumer:

```json
{
  "identity": "...",
  "provenance": "...",
  "observation": "...",
  "governance": "..."
}
```

`integrity` is excluded from its own payload identity.

Canonicalization is sorted compact JSON encoded as UTF-8 and hashed with SHA-256.

The received artifact must physically contain:

```text
integrity.hash_algorithm == "sha256"
integrity.canonicalization == "sorted-json-utf8"
```

Schema defaults are not used as substitutes for those trust-boundary inputs.

## Signature verification

The adapter accepts compact JWS with:

```text
alg == "EdDSA"
```

The selected JWK must be consumer-controlled and must use:

```text
kty == "OKP"
crv == "Ed25519"
```

`integrity.key_id` selects a key from the JWKS supplied by the VERITAS deployment. Public-key material supplied by the artifact does not bootstrap trust.

When the JWS protected header contains `kid`, it must equal `integrity.key_id`.

The following signed claims must exactly match the received contract:

- `payload_hash`
- `hash_algorithm`
- `schema_version`
- `request_id`
- `timestamp`

## Measurement semantics

The first interoperability slice preserves NeoMundi's epistemic boundary:

- coverage must be within `0.0` and `1.0`;
- `complete` requires coverage `1.0`;
- `partial` requires coverage below `1.0`;
- a `measured` signal requires a numeric value;
- `not_measured` and `insufficient_coverage` require `null`;
- `null` is never promoted to zero, safe, normal, or within-bounds meaning;
- `not_assessed` remains a bounded measurement statement;
- `single_request` remains a single-observation scope and does not establish persistence, recurrence, frequency, trend, or drift.

The adapter also requires explicit measurement limitations and a measurement boundary.

## Governance semantics

For this PoC adapter, the received artifact must explicitly contain:

```text
governance.governance_boundary.authorization_status == "not_applicable"
governance.governance_boundary.execution_permission_changed == false
```

Omission of `execution_permission_changed` is not interpreted as false.

Supported review recommendation values are:

```text
not_indicated
recommended
required
```

These values are preserved as provider advisory evidence. They do not directly produce a VERITAS HOLD, DENY, approval requirement, or execution decision.

## Normalized evidence mapping

The verified RGC artifact maps to provider-neutral evidence using deterministic identities.

The RGC request identifier becomes the provider artifact id. The verified RGC timestamp is used as both `observed_at` and `issued_at` for this first adapter because RGC v0.2 exposes one contract timestamp rather than separate observation and issuance timestamps. This is a protocol mapping, not a claim that two independently observed events occurred.

RGC v0.2 does not supply an expiry semantic, so the adapter emits:

```text
expires_at = None
```

Deployments accepting RGC v0.2 must therefore configure the provider-neutral `ExternalMeasurementTrustPolicy` with an explicit freshness limit and `require_expiry=False`. The generic default is not weakened.

Replay protection remains owned by the existing provider-neutral `ExternalMeasurementReplayGuard`; the adapter does not introduce a second replay subsystem.

## Trusted-key policy

PR2 performs no live JWKS network lookup. Trusted JWKS material is injected through VERITAS-controlled configuration when constructing `NeoMundiRgcV02Verifier`.

The verifier policy hash deterministically binds the configured trusted JWKS, verifier identity, trust level, protocol version, canonicalization, hash algorithm, and JWS algorithm. The existing generic trust policy must independently approve that exact verifier binding.

## Tests versus live interoperability

The test suite generates non-production Ed25519 keys and synthetic signed RGC v0.2 artifacts to verify deterministic positive and negative paths.

Those fixtures prove VERITAS adapter behavior only. They are not evidence that a real NeoMundi runtime observation has been verified.

The next interoperability milestone after this adapter is merged is:

```text
real NeoMundi runtime observation
        ↓
real NeoMundi-generated signed RGC v0.2 artifact
        ↓
independent VERITAS verification
        ↓
VerifiedExternalMeasurementEvidence
        ↓
External PoC #1 evidence chain
```

## Non-goals

This adapter does not modify:

- native v2 authorization;
- single-use authorization consumption;
- credential resolution;
- durable dispatch intent;
- external-effect retry behavior;
- `EFFECT_UNKNOWN` handling;
- BindReceipt or Outcome semantics;
- reconciliation;
- crash recovery;
- the frozen Decision-to-Effect execution architecture.

It also performs no external effects and no network calls.
