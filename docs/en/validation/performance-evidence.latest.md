# Performance Evidence

## Summary table
| Key | Value |
| --- | --- |
| schema_version | performance_evidence.v1 |
| generated_at | 1970-01-01T00:00:00+00:00 |
| measurement_mode | deterministic_fixture |
| sample_count | 3 |
| warmup_count | 0 |

## Metrics table
| Metric | Status | Samples | p95_ms | Notes |
| --- | --- | --- | --- | --- |
| api_health_route | ok | 3 | 8.3 | deterministic fixture; not production SLA |
| trustlog_append_local | ok | 3 | 3.3 | deterministic fixture; not production SLA |
| bind_eval_local | ok | 3 | 4.3 | deterministic fixture; not production SLA |

## Interpretation boundaries
- This artifact is reviewer-facing deterministic fixture evidence.
- This artifact is not a production SLA.
- This artifact does not include external LLM provider latency.
- This artifact does not include customer infrastructure latency.
- Results should be re-measured in customer PoC environments.
- This artifact is intended to validate exporter structure, reporting format, and deterministic evidence plumbing.
