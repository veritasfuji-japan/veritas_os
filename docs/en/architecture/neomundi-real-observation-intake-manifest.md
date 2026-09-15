# NeoMundi Real Observation Intake Manifest v1

This manifest binds one real-observation PoC handoff packet before VERITAS performs key-provenance or provider verification.

The machine-readable contract is:

`schemas/neomundi_real_observation_intake_manifest.schema.json`

A template is available at:

`docs/en/architecture/neomundi-real-observation-intake-manifest.example.json`

The manifest binds the exact RGC artifact, public JWKS, and Trusted Public Key Provenance Receipt by file SHA-256, and also binds the expected RGC request ID, key ID, and signer identity.

It is not a trust root. It does not authenticate NeoMundi, prove the handoff channel, establish evidence freshness, replace the Trusted Public Key Provenance Receipt, or create execution authority. `received_at` is audit metadata only and is not treated as trusted UTC.

The official real-observation CLI validates the manifest before provenance verification, provider verification, or replay-state consumption. Any mismatch fails closed.
