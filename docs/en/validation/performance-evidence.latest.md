# Performance Evidence Artifact

## Scope
Reviewer-facing latency evidence for CI-safe local measurements.

## Summary table
| Metric | Value |
| --- | --- |
| measurement_mode | deterministic_fixture |
| sample_count | 3 |
| warmup_count | 0 |
| status | ok |

## Metrics table
| Name | Category | p50 ms | p95 ms | p99 ms | Status | Notes |
| --- | --- | ---: | ---: | ---: | --- | --- |
| api.health.get | api_route_smoke | 1.100 | 1.190 | 1.198 | ok |  |
| api.status.get | api_route_smoke | 1.800 | 1.890 | 1.898 | ok |  |
| bind.catalog_consistency | bind_boundary | 0.300 | 0.300 | 0.300 | ok |  |
| bind.classify | bind_boundary | 0.200 | 0.290 | 0.298 | ok |  |
| bind.validate_registry | bind_boundary | 0.400 | 0.490 | 0.498 | ok |  |
| decide.deterministic.fixture | decide_deterministic | 2.100 | 2.190 | 2.198 | ok | External LLM provider latency is excluded. |
| trustlog.append.local | trustlog_append | 1.000 | 1.090 | 1.098 | ok | TrustLog measurements use the configured local/test backend unless otherwise noted. |

## Failures / not measured
- None

## Interpretation boundaries
- This artifact is CI-safe local evidence, not a production SLA.
- This artifact does not include external LLM provider latency unless explicitly measured.
- This artifact does not include customer infrastructure latency.
- Results should be re-measured in customer PoC environments.
- TrustLog measurements use the configured local/test backend unless otherwise noted.

## How to regenerate
```bash
python -m scripts.performance.export_performance_evidence
```
