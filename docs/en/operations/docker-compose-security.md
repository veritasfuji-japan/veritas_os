# Docker Compose Security Notes

## 1. Purpose

This note defines local Docker Compose credential handling for VERITAS OS.

## 2. Why compose credentials are explicit

`docker-compose.yml` intentionally does not provide default database or admin BFF credentials. This prevents accidental startup with weak, known values.

## 3. Required local `.env` values

1. Copy `.env.example` to `.env`.
2. Replace every `CHANGE_ME` value.
3. Provide explicit values for:
   - `VERITAS_DB_PASSWORD`
   - `VERITAS_DATABASE_URL`
   - `VERITAS_BFF_SESSION_TOKEN`
   - `VERITAS_BFF_AUTH_TOKENS_JSON`

Do not commit `.env`.

## 4. Generating local-only secrets

Use strong random values for local controlled review. Keep them local and unshared.

## 5. What not to do

- Do not run compose with placeholder values.
- Do not reuse local compose secrets in staging or production.
- Do not commit real secrets.

## 6. Production boundary

Compose setup is for local or controlled PoC use unless separately reviewed. Production should use managed secrets and a managed database where appropriate. This document is not production SLA and does not claim production hardening.

## 7. Troubleshooting

If compose fails before startup, check missing required variables in `.env` and ensure `VERITAS_BFF_SESSION_TOKEN` is a key in `VERITAS_BFF_AUTH_TOKENS_JSON`.
