# Value Core Separation

Value Core separates three spaces:

- `normative_weights`
- `operational_preferences`
- `personal_preferences`

Governance scoring uses `normative_weights` only. Operational and personal preferences do not affect compliance or governance scores (`ValueResult.total`).
`DEFAULT_WEIGHTS` and `ValueProfile.weights` are compatibility views only and may include legacy operational/personal keys.
They must not be used for governance scoring.
Use `DEFAULT_NORMATIVE_WEIGHTS` as the governance-scoring source of truth.
`personal_preferences` currently allowlists `sauna_less` as a canonical personal key.
Personal preferences are preserved for compatibility and user-level storage, but excluded from governance scoring.

Legacy compatibility is preserved for old `weights` payloads and legacy Japanese keys.

This avoids mixing developer workflow preferences with regulated decision values.
