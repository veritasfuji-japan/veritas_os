# Environment Variable Reference

> **Last updated**: 2026-04-11  
> **Source of truth**: `veritas_os/core/config.py`, individual modules  
> **See also**: [`postgresql-production-guide.md`](postgresql-production-guide.md) for PostgreSQL-specific production guidance

All environment variables used by Veritas OS, grouped by category.
Variables prefixed with `VERITAS_` are project-specific.

---

## LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | LLM backend provider (`openai`, `anthropic`, `google`, `ollama`, `openrouter`) |
| `LLM_MODEL` | `gpt-4.1-mini` | Model identifier for the selected provider |
| `LLM_TIMEOUT` | `60.0` | API call timeout in seconds (range: 5.0–300.0) |
| `LLM_CONNECT_TIMEOUT` | `10.0` | Connection timeout in seconds (range: 1.0–60.0) |
| `LLM_MAX_RETRIES` | `3` | Number of retry attempts (range: 0–10) |
| `LLM_RETRY_DELAY` | `2.0` | Delay between retries in seconds (range: 0.1–30.0) |
| `LLM_MAX_RESPONSE_BYTES` | `16777216` (16 MB) | Maximum response size to prevent memory exhaustion |
| `OPENAI_API_KEY` | *(required)* | OpenAI API authentication key |
| `OPEN_API_KEY` | — | Fallback for `OPENAI_API_KEY` |
| `OPENAI_API_KEY_VERITAS` | — | Veritas-specific OpenAI key fallback |

---

## API Authentication & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_API_KEY` | `""` | Primary authentication key for protected endpoints |
| `VERITAS_API_SECRET` | `""` | HMAC signature verification secret — **required** in production |
| `VERITAS_API_SECRET_REF` | `""` | External secret reference name/path |
| `VERITAS_SECRET_PROVIDER` | `""` | Secret manager provider (`vault`, `aws_secrets_manager`, `gcp_secret_manager`, `azure_key_vault`, `kms`) |
| `VERITAS_ENFORCE_API_SECRET` | `true` | Fail startup if API secret is missing (auto-relaxed under pytest) |
| `VERITAS_ENFORCE_API_SECRET_IN_TESTS` | `false` | Override auto-relaxation in test environments |
| `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER` | `false` | Require external secret manager for API secret |

---

## Authentication Store

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_AUTH_SECURITY_STORE` | `memory` | Auth store backend (`memory` or `redis`) — use `redis` in production |
| `VERITAS_AUTH_REDIS_URL` | `""` | Redis connection URL when using redis backend |
| `VERITAS_AUTH_STORE_FAILURE_MODE` | `closed` | `closed` (deny on error) or `open` (allow on error) — **never** use `open` in production |
| `VERITAS_AUTH_ALLOW_FAIL_OPEN` | `false` | Explicit opt-in to allow fail-open (test environments only) |
| `VERITAS_ALLOW_SSE_QUERY_API_KEY` | `false` | Permit API key in SSE query parameters (⚠️ security risk, ignored in production profiles) |
| `VERITAS_ACK_SSE_QUERY_API_KEY_RISK` | `false` | Acknowledgment of SSE query API key risk |
| `VERITAS_ALLOW_WS_QUERY_API_KEY` | `false` | Permit API key in WebSocket query parameters (⚠️ security risk, ignored in production profiles) |
| `VERITAS_ACK_WS_QUERY_API_KEY_RISK` | `false` | Acknowledgment of WebSocket query API key risk |
| `VERITAS_TRUSTED_PROXIES` | `""` | Comma-separated trusted proxy IPs for X-Forwarded-For handling |

---

## Encryption & TrustLog

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_ENCRYPTION_KEY` | *(required)* | Base64-encoded 32-byte key for AES-256-GCM encryption |
| `VERITAS_ENCRYPTION_LEGACY_DECRYPT` | `false` | Enable legacy `ENC:<payload>` decryption during migrations |
| `VERITAS_TRUSTLOG_SIGNER_BACKEND` | `file` | TrustLog signature backend (`file` for local/dev/test only, `aws_kms` for `secure`/`prod` — requires `managed_signing` capability) |
| `VERITAS_TRUSTLOG_KMS_KEY_ID` | `""` | AWS KMS Ed25519 key identifier/ARN required when `VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms` |
| `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD` | `0` | Emergency break-glass for `file` signer in `secure` posture only. **Ignored in `prod` posture** — insecure signers are unconditionally refused in production |
| `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` | `""` | Optional mirror path for WORM (Write-Once-Read-Many) audit log |
| `VERITAS_TRUSTLOG_WORM_HARD_FAIL` | `0` | Fail hard if WORM mirror write fails (`0` = warn, `1` = error) |
| `VERITAS_TRUSTLOG_ANCHOR_BACKEND` | `local` | TrustLog anchor backend (`local` = local spool receipt, `noop` = explicitly skip anchoring) |
| `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` | `""` | Local spool path used by `VERITAS_TRUSTLOG_ANCHOR_BACKEND=local` |
| `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED` | `0` | Require transparency log anchoring (`0` = optional, `1` = required) |

### TrustLog transparency anchoring roadmap

- **Phase 1 (current)**: local/internal anchoring via structured backend receipts.
  - `local` backend writes to local spool JSONL and stores a normalized
    `anchor_receipt` in witness entries.
  - `noop` backend emits a structured "skipped" receipt for local/dev flows.
- **Future phase**: external timestamp authorities (RFC3161 TSA or equivalent).
  - The witness schema is prepared via `anchor_backend`, `anchor_status`,
    and `anchor_receipt`, so a TSA backend can be added without structural
    TrustLog refactors.

---

## Runtime & Environment Profile

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_ENV` | `""` | Deployment profile: `production`, `staging`, `dev`, `test`, `demo` |
| `VERITAS_RUNTIME_ROOT` | `<repo>/runtime` | Base directory for runtime data and logs |
| `VERITAS_RUNTIME_NAMESPACE` | *(derived from `VERITAS_ENV`)* | Data separation namespace (`prod`, `dev`, `test`, `demo`) |
| `VERITAS_DEBUG_MODE` | `false` | Enable verbose debug logging |

---

## Paths & Directories

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_MEMORY_DIR` | *(auto-derived)* | Directory for memory/state persistence |
| `VERITAS_MEMORY_PATH` | *(auto-derived)* | Specific memory file path override |
| `VERITAS_LOG_DIR` | `<runtime>/logs` | Log directory path |
| `VERITAS_LOG_ROOT` | — | Root log directory override |
| `VERITAS_ENCRYPTED_LOG_ROOT` | — | Base path for encrypted logs |
| `VERITAS_DATA_DIR` | — | Data directory root |
| `VERITAS_REQUIRE_ENCRYPTED_LOG_DIR` | `false` | Enforce log paths within `VERITAS_ENCRYPTED_LOG_ROOT` |
| `VERITAS_MEMORY_DIR_ALLOWLIST` | `""` | Comma-separated allowed memory directories (security restriction) |
| `VERITAS_MEMORY_CACHE_TTL` | `5.0` | Memory cache time-to-live in seconds |
| `VERITAS_LOG_MAX_LINES` | — | Log rotation threshold (max lines before rotation) |
| `VERITAS_ALLOW_EXTERNAL_PATHS` | `false` | Allow external paths for log/dataset directories |
| `VERITAS_DATASET_DIR` | — | Dataset storage directory |

---

## CORS & Network

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_CORS_ALLOW_ORIGINS` | `""` | Comma-separated CORS allow-list (e.g., `http://localhost:3000`) |
| `VERITAS_MAX_REQUEST_BODY_SIZE` | *(middleware default)* | Maximum request body size in bytes |
| `VERITAS_SHUTDOWN_DRAIN_SEC` | `10` | Graceful shutdown drain time for in-flight requests |
| `VERITAS_API_BASE` / `VERITAS_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |
| `VERITAS_HTTP_TIMEOUT` | `10` | HTTP request timeout for scripts |

---

## Pipeline & Decision Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_MEMORY_SEARCH_LIMIT` | `8` | Memory search result limit |
| `VERITAS_EVIDENCE_TOP_K` | `5` | Top-K evidence items per query |
| `VERITAS_MAX_PLAN_STEPS` | `10` | Maximum plan steps |
| `VERITAS_DEBATE_TIMEOUT` | `30` | Debate timeout in seconds |
| `VERITAS_PERSONA_UPDATE_WINDOW` | `50` | Persona auto-adjust window |
| `VERITAS_PERSONA_BIAS_INCREMENT` | `0.05` | Persona bias increment |
| `VERITAS_MIN_EVIDENCE` | `1` | Minimum evidence threshold |
| `VERITAS_MAX_UNCERTAINTY` | `0.60` | Maximum acceptable uncertainty |
| `VERITAS_EVIDENCE_MAX` | `50` | Maximum evidence items in pipeline |
| `VERITAS_PIPELINE_WARN` | `true` | Emit pipeline warnings |
| `VERITAS_POC_MODE` | `false` | Proof-of-concept mode (non-production testing) |

---

## Scoring Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_INTENT_WEATHER_BONUS` | `0.4` | Intent-based weather query bonus |
| `VERITAS_INTENT_HEALTH_BONUS` | `0.4` | Intent-based health query bonus |
| `VERITAS_INTENT_LEARN_BONUS` | `0.35` | Intent-based learning query bonus |
| `VERITAS_INTENT_PLAN_BONUS` | `0.3` | Intent-based planning query bonus |
| `VERITAS_QUERY_MATCH_BONUS` | `0.2` | Query matching bonus |
| `VERITAS_HIGH_STAKES_THRESHOLD` | `0.7` | High-stakes detection threshold |
| `VERITAS_HIGH_STAKES_BONUS` | `0.2` | Bonus when high-stakes is detected |
| `VERITAS_PERSONA_BIAS_MULTIPLIER` | `0.3` | Persona bias multiplier |
| `VERITAS_TELOS_SCALE_BASE` | `0.9` | Telos score scale base |
| `VERITAS_TELOS_SCALE_FACTOR` | `0.2` | Telos score scale factor |

---

## Risk & Safety

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_SAFETY_THRESHOLD` | `0.8` | Safety score threshold |
| `VERITAS_PII_SAFE_RISK_CAP` | `0.40` | Risk cap when PII is safely handled |
| `VERITAS_NAME_LIKE_RISK_CAP` | `0.20` | Risk cap for name-like-only detections |
| `VERITAS_LOW_EVIDENCE_PENALTY` | `0.10` | Penalty for low evidence |
| `VERITAS_SAFETY_HEAD_ERROR_RISK` | `0.30` | Base risk when safety head errors occur |
| `VERITAS_TELOS_RISK_SCALE` | `0.10` | Telos-based risk scale factor |
| `VERITAS_VALUE_BOOST_MAX` | `0.05` | Maximum policy value boost factor |
| `VERITAS_RISK_EMA_WEIGHT` | `0.15` | Risk exponential moving average weight |
| `VERITAS_TELOS_EMA_DELTA` | `0.10` | Telos EMA delta |
| `VERITAS_SAFETY_MODE` | — | LLM safety check mode (`heuristic`, `local`, or API-based) |
| `VERITAS_SAFETY_MODEL` | `gpt-4.1-mini` | Model used for safety checks |

---

## Capability Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_CAP_KERNEL_REASON` | `true` | Enable kernel reasoning |
| `VERITAS_CAP_KERNEL_STRATEGY` | `true` | Enable kernel strategy selection |
| `VERITAS_CAP_KERNEL_SANITIZE` | `true` | Enable kernel PII sanitization |
| `VERITAS_CAP_FUJI_TOOL_BRIDGE` | `true` | Enable Fuji tool bridge |
| `VERITAS_CAP_FUJI_TRUST_LOG` | `true` | Enable Fuji trust logging |
| `VERITAS_CAP_FUJI_YAML_POLICY` | `false` | Enable YAML-based Fuji policies |
| `VERITAS_CAP_MEMORY_POSIX_FILE_LOCK` | `true` | Enable POSIX file locking for memory |
| `VERITAS_CAP_MEMORY_JOBLIB_MODEL` | `false` | Enable joblib model for memory |
| `VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS` | `false` | Enable sentence-transformers for memory |
| `VERITAS_CAP_CONTINUATION_RUNTIME` | `false` | Enable continuation runtime |
| `VERITAS_CAP_EMIT_MANIFEST` | `true` | Emit capability manifest on import |

---

## Governance & Compliance

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES` | `1` | Require dual-approval for policy changes |
| `VERITAS_GOVERNANCE_ENFORCE_RBAC` | `1` | Enforce role-based access control |
| `VERITAS_GOVERNANCE_ALLOWED_ROLES` | `admin,compliance_owner` | Comma-separated roles for governance operations |
| `VERITAS_GOVERNANCE_TENANT_ID` | `""` | Tenant ID for multi-tenant isolation |
| `VERITAS_GOVERNANCE_BACKEND` | `file` | Governance repository backend (`file` or `postgresql`) |
| `VERITAS_EU_AI_ACT_MODE` | `false` | Enable EU AI Act compliance features |
| `VERITAS_HUMAN_REVIEW_WEBHOOK_URL` | — | Webhook URL for human review escalation notifications |
| `VERITAS_HUMAN_REVIEW_SLA_SECONDS` | *(module default)* | SLA timeout for human review completion |
| `VERITAS_CONTEST_CONTACT` | — | Contact info for EU AI Act appeal/contest process |

---

## Fuji Policy

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_FUJI_POLICY` | — | Path to Fuji policy YAML file |
| `VERITAS_FUJI_STRICT_POLICY_LOAD` | `0` | Fail hard on policy load errors (`0` = warn, `1` = error) |
| `VERITAS_ENABLE_DIRECT_FUJI_API` | `false` | Enable direct Fuji API calls |

---

## Web Search / SSRF Prevention

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_WEBSEARCH_URL` | `""` | Web search service endpoint URL |
| `VERITAS_WEBSEARCH_KEY` | `""` | API key for web search service |
| `VERITAS_WEBSEARCH_HOST_ALLOWLIST` | `""` | Comma-separated allowed hosts for web search |
| `VERITAS_WEBSEARCH_ENABLE_TOXICITY_FILTER` | `true` | Filter toxic content from search results |

---

## PostgreSQL / Storage Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_MEMORY_BACKEND` | `json` | Memory storage backend (`json` or `postgresql`) |
| `VERITAS_TRUSTLOG_BACKEND` | `jsonl` | TrustLog storage backend (`jsonl` or `postgresql`) |
| `VERITAS_DATABASE_URL` | *(required when backend=postgresql)* | PostgreSQL DSN, e.g. `postgresql://veritas:veritas@localhost:5432/veritas` |
| `VERITAS_DB_POOL_MIN_SIZE` | `2` | Minimum idle connections in the pool |
| `VERITAS_DB_POOL_MAX_SIZE` | `10` | Maximum connections in the pool |
| `VERITAS_DB_CONNECT_TIMEOUT` | `5` | TCP connect timeout in seconds |
| `VERITAS_DB_STATEMENT_TIMEOUT_MS` | `30000` | Per-statement timeout in milliseconds |
| `VERITAS_DB_SSLMODE` | `prefer` | libpq sslmode (`disable`, `prefer`, `require`, `verify-full`) |
| `VERITAS_DB_AUTO_MIGRATE` | `false` | Run pending SQL migrations on startup |

---

## Replay & Persistence

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_REPLAY_STRICT` | `false` | Enable strict replay enforcement |
| `VERITAS_PIPELINE_VERSION` | *(auto-detect)* | Injected pipeline version for replay validation |
| `VERITAS_REPLAY_ENFORCE_MODEL_VERSION` | `true` | Enforce model version matching during replay |
| `VERITAS_REPLAY_REQUIRE_MODEL_VERSION` | `true` | Require model version info in replay |
| `VERITAS_MODEL_NAME` | `gpt-5-thinking` | Model name for serialization and replay |
| `VERITAS_API_VERSION` | `veritas-api 1.x` | API version identifier |
| `VERITAS_KERNEL_VERSION` | `core-kernel 0.x` | Kernel version identifier |
| `VERITAS_VERSION` | `1.0.0` | Application version string |

---

## Self-Healing & Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_SELF_HEALING_ENABLED` | `true` | Enable self-healing recovery mechanisms |
| `VERITAS_ALERT_UNC` | `0.50` | Uncertainty threshold for alert triggers |
| `VERITAS_HEAL_ON_HIGH` | `true` | Trigger healing on high uncertainty |
| `VERITAS_HEAL_TIMEOUT_SEC` | *(module default)* | Healing operation timeout in seconds |
| `VERITAS_HEALTH_ALLOW_PUBLIC` | `false` | Allow unauthenticated health check access |

---

## External Integrations

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_GITHUB_TOKEN` | `""` | GitHub API token for repository operations |

---

## Workers & Server

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_CONCURRENCY` | — | Number of web worker processes |
| `UVICORN_WORKERS` | — | Number of uvicorn worker processes |
| `VERITAS_ALLOW_EPHEMERAL_DASHBOARD_PASSWORD` | `false` | Allow temporary dashboard password generation |

---

## Frontend (Next.js)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_VERITAS_API_BASE_URL` | — | Browser-facing API base URL (⚠️ `NEXT_PUBLIC_` = browser-exposed) |

---

## CLI & Scripts

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITAS_USER_ID` | `cli` | User identifier for CLI operations |
| `VERITAS_REPO_ROOT` | — | Repository root path for scripts |
| `VERITAS_DOCTOR_REPORT` | *(module default)* | Path to doctor/health report output |
| `VERITAS_BENCH_LOG_DIR` | *(module default)* | Directory for benchmark logs |
| `VERITAS_COVERAGE_JSON` | — | Path to coverage map JSON |
| `VERITAS_EXPERIMENTS_PER_DAY` | `3` | Target experiments per day |
