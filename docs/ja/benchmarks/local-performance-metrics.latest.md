# ローカル性能メトリクス実測artifact

- 英語版が正本であり、日本語版は補助説明です。
- `docs/en/benchmarks/local-performance-metrics.latest.json` の補助説明である。
- deterministic local measurement artifact である。
- 本番レイテンシではない。
- 外部LLM/APIは呼んでいない。
- 本番SLAではない。
- 第三者認証ではない。
- 顧客環境での測定ではない。

## 英語正本

- [Local Performance Metrics Artifact](../../en/benchmarks/local-performance-metrics.latest.md)
- [Local Performance Metrics JSON](../../en/benchmarks/local-performance-metrics.latest.json)

## Scope

このartifactは、deterministicなローカルベンチマーク1回分の実測結果です。本番レイテンシや顧客環境での性能を示すものではありません。

## Artifact

- JSON: `docs/en/benchmarks/local-performance-metrics.latest.json`
- 補助サマリー（本ファイル）: `docs/ja/benchmarks/local-performance-metrics.latest.md`

## How it was generated

```bash
python scripts/benchmarks/run_performance_metrics.py --iterations 100 --warmup 10 --output docs/en/benchmarks/local-performance-metrics.latest.json
```

## Metrics summary

local deterministic artifactのみ（本番レイテンシではない）:

| Field | Value |
| --- | --- |
| schema_version | performance_metrics.v1 |
| scenario | local_deterministic_smoke |
| iterations | 100 |
| warmup | 10 |
| mean_ms | 0.010114 |
| median_ms | 0.008882 |
| p95_ms | 0.015959 |
| p99_ms | 0.024828 |
| min_ms | 0.008606 |
| max_ms | 0.029875 |
| success | 100 |
| failure | 0 |

## Interpretation boundaries

- deterministic local benchmark only.
- 外部LLM/API呼び出しなし。
- 本番SLAではない。
- 第三者認証ではない。
- 顧客環境測定ではない。

## Next measurement targets

- API route latency
- Bind boundary decision latency
- TrustLog append latency, JSONL and PostgreSQL separately
- one-day PoC end-to-end scenario latency
- provider adapter overhead
- cost-per-request estimation when external LLM providers are intentionally enabled
