# Provider Support Matrix

## Purpose

This document clarifies current model-provider support tiers for VERITAS OS so enterprise reviewers, investors, and customers can evaluate provider dependency boundaries without ambiguity.

## Provider dependency positioning

VERITAS is designed with a provider abstraction boundary, but the current production-tier provider is OpenAI unless this matrix states otherwise. Planned or experimental providers should not be treated as production-supported for regulated workflows, external customer demos, or enterprise procurement reviews without additional validation.

Provider support does not imply that a provider satisfies a customer’s data residency, security, procurement, legal, or regulatory requirements. Each organization remains responsible for reviewing provider terms, data handling, retention, residency, model behavior, and risk controls.

## Current support tiers

Support tiers are sourced from `veritas_os/core/llm_client.py` (`PROVIDER_SUPPORT_TIER`).

## What “production” means

Production support means:

- a documented configuration path exists;
- the provider is exercised in current tests or smoke paths where applicable;
- the provider is supported by the current runtime client surface;
- known failure behavior is defined.

Production support does **not** mean:

- legal approval for all customers;
- data residency requirements are satisfied;
- on-premises or private-cloud support is guaranteed;
- regulated deployment certification exists;
- model behavior is equivalent across providers.

## What “planned” means

Planned means an intended provider path exists, but it is not production-supported and should not be treated as production-ready for governed decision flows.

## What “experimental” means

Experimental means developer-oriented or adapter-level support only. It may change without stability guarantees and is not production SLA support.

## Current provider matrix

| Provider | Tier | Current status | Intended use | Known limitations |
|---|---|---|---|---|
| OpenAI | Production | Default supported provider | Current PoC / runtime path | Requires valid credentials and organization-specific provider policy review |
| Anthropic | Planned | Not production-supported yet | Future provider adapter | Not validated for current governed decision path |
| Google | Planned | Not production-supported yet | Future provider adapter | Not validated for current governed decision path |
| Ollama / local models | Experimental | Local/experimental adapter only | Developer experiments / local evaluation | Not production SLA, not validated for regulated workflow |
| OpenRouter / compatible gateway | Experimental | Gateway-dependent adapter path | Provider abstraction experiments | Gateway behavior, data handling, and latency must be reviewed |

## Known limitations

- Current production-tier support is OpenAI only.
- Provider support tiers do not certify provider-side legal/compliance posture.
- Multi-provider parity is not implied by abstraction interfaces alone.
- Anthropic has offline contract coverage for request formatting, response parsing, header construction, model allowlist behavior, planned-tier warnings, and sanitized error handling. It remains Planned and must not be treated as production-supported without additional live integration validation, operational review, benchmark evidence, and customer/provider policy review.

## What changes when using a non-OpenAI provider

- Latency, rate limits, model behavior, and error modes can differ.
- Request/response conventions may differ by provider or gateway.
- Security, legal, and procurement reviews must be repeated per provider.
- Regulated workflow readiness must be re-validated before production claims.

## Enterprise review checklist

- Confirm required provider tier for the target workflow.
- Review provider terms, retention, and data handling policies.
- Validate failure handling and fallback behavior for that provider.
- Re-run governance and evidence checks in the target environment.
- Verify regional/legal constraints in customer deployment scope.

## Roadmap

VERITAS targets broader provider neutrality over time through explicit adapter validation and production-readiness gates. Until then, treat OpenAI as the current production tier unless code and docs explicitly state otherwise.

## Non-goals

- This matrix is not legal advice.
- This matrix is not a certification statement.
- This matrix is not a guarantee of on-premises/private-cloud support.
- This matrix does not promise equal behavior across all providers.
