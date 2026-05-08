# Docker Compose Security Notes

## Purpose

This note explains local Docker Compose credential handling for VERITAS OS and sets clear non-production boundaries.

## Why compose credentials are explicit

docker-compose.yml intentionally does not provide default database or admin BFF credentials.
This fail-fast behavior prevents accidental startup with known credentials during PoC or external review usage.

## Required local `.env` values

Copy `.env.example` to `.env`.
Replace every `CHANGE_ME` value.
At minimum, set:

- `VERITAS_DB_PASSWORD`
- `VERITAS_DATABASE_URL`
- `VERITAS_BFF_SESSION_TOKEN`
- `VERITAS_BFF_AUTH_TOKENS_JSON`

Do not commit `.env`.

## Generating local-only secrets

Use locally generated random values for database passwords and BFF session tokens.
Keep them machine-local and rotate when sharing demos between operators.

## What not to do

- Do not restore default DB passwords or fixed admin session tokens.
- Do not use local compose secrets in shared, staging, or production environments.
- Do not commit `.env` or real secret values.

## Production boundary

Production should use managed secrets and a managed database where appropriate.
This is not production SLA and does not claim production hardening.

## Troubleshooting

If Compose fails before startup with `${VAR:?...}` errors, required variables are missing.
Re-check `.env` and ensure every required key is present with non-placeholder values.
