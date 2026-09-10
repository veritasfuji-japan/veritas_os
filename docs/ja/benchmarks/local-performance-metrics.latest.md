# ローカル性能メトリクス実測artifact

- 英語版が正本であり、日本語版は補助説明です。
- `docs/en/benchmarks/local-performance-metrics.latest.json` の補助説明である。
- deterministic local measurement artifact である。
- 本番レイテンシではない。
- 外部LLM/APIは呼んでいない。
- 本番SLAではない。
- 第三者認証ではない。
- 顧客環境での測定ではない。

## Rebaseline status

現在GitHubにcommitされている `docs/en/benchmarks/local-performance-metrics.latest.json` は、
2026-05-09に生成されたもので、測定対象のGit source commit SHAを記録していません。
そのためTASK-011 Phase Aでは、このcommit済みartifactを
`STALE_PRE_REBASELINE_REFERENCE` と分類しています。現在のhead性能として扱ってはいけません。

TASK-011 Phase Bでは `.github/workflows/benchmark-rebaseline-phase-b.yml` により、
source SHAに結び付いたdeterministic local measurementを生成します。Pull Requestではcheckoutした
PR headを検証し、merge後のpush-to-mainでは、その時点の正確な `main` commitを測定して、JSONと
run manifestをGitHub Actions artifactとして保存します。Phase Bにおけるcurrent-headの正本証拠は、
下記の2026年5月のcommit済みJSONではなく、そのsource-SHA-bound Actions artifactです。

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

以下はpre-rebaselineのhistorical local deterministic artifactのみであり、current-headでも本番レイテンシでもありません。

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
- commit済みの2026年5月の値はcurrent-head benchmarkではない。

## Next measurement targets

- API route latency
- Bind boundary decision latency
- TrustLog append latency, JSONL and PostgreSQL separately
- one-day PoC end-to-end scenario latency
- provider adapter overhead
- cost-per-request estimation when external LLM providers are intentionally enabled
