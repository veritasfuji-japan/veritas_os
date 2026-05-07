# Value Core Separation

Value Core separates three spaces:

- `normative_weights`
- `operational_preferences`
- `personal_preferences`

Governance scoring uses `normative_weights` only. Operational and personal preferences do not affect compliance or governance scores (`ValueResult.total`).

Legacy compatibility is preserved for old `weights` payloads and legacy Japanese keys.

This avoids mixing developer workflow preferences with regulated decision values.
