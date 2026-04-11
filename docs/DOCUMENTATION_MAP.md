# Documentation Map (Bilingual Structure)

## Entrypoints
- English: [docs/en/README.md](en/README.md)
- 日本語: [docs/ja/README.md](ja/README.md)

## Operations & Production Guides
- PostgreSQL Production Guide: [docs/postgresql-production-guide.md](postgresql-production-guide.md)
- Security Hardening Checklist: [docs/security-hardening.md](security-hardening.md)
- Database Migrations (Alembic): [docs/database-migrations.md](database-migrations.md)
- Backend Parity Coverage: [docs/BACKEND_PARITY_COVERAGE.md](BACKEND_PARITY_COVERAGE.md)
- Legacy Path Cleanup: [docs/legacy-path-cleanup.md](legacy-path-cleanup.md)
- Operational Readiness Runbook: [docs/OPERATIONAL_READINESS_RUNBOOK.md](OPERATIONAL_READINESS_RUNBOOK.md)
- Production Validation: [docs/PRODUCTION_VALIDATION.md](PRODUCTION_VALIDATION.md)
- Release Process: [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md)
- Environment Variable Reference: [docs/env-reference.md](env-reference.md)
- Dependency Profiles: [docs/dependency-profiles.md](dependency-profiles.md)

## Language split policy
- `docs/en/**`: English primary docs.
- `docs/ja/**`: Japanese primary docs (including legacy mixed-language docs pending split).

## Translation pairing status (high-level)
- `README.md` ↔ `README_JP.md`
- `veritas_os/README.md` ↔ `veritas_os/README_JP.md`
- Review archives are mostly Japanese-only at this time.

## Legacy consolidation completed
- Consolidated `docs/review/*` and `docs/reviews/*` into `docs/ja/reviews/` and `docs/en/reviews/`.
- Moved root-level review markdown files into review folders.
- Moved audit and operations documents to language-specific paths.
