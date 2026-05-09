# One-Day PoC パフォーマンスベンチマークレポート

## 英語正本

- [One-Day PoC Performance Benchmark](../../en/poc/one-day-poc-performance-report.md)

## 目的

これは One-Day PoC 向けの **local HTTP PoC benchmark** です。
実行には、起動中の local/configured VERITAS API server と `VERITAS_API_KEY` が必要です。

また、これは deterministic local performance metrics artifact とは別物です。
deterministic local non-HTTP artifact は
`docs/en/benchmarks/local-performance-metrics.latest.md` を参照してください。

## 実行方法

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py --runs 5 --warmup 1 --base-url http://127.0.0.1:8000 --out-json /tmp/one-day-poc-benchmark.json --out-md /tmp/one-day-poc-benchmark.md
```

## 非主張境界（誤解防止）

- これは local HTTP PoC benchmark であり、本番レイテンシ測定ではありません。
- 本番SLAではない。
- 第三者認証ではない。
- 顧客環境測定ではない。
- 外部LLM/provider latency は、configured local server が明示的にproviderを呼ぶ場合を除き測定対象ではありません。

## 関連する証跡パック

- One-Day PoCの証跡収集、成功条件、失敗条件は `docs/ja/poc/one-day-poc-evidence-pack.md` を参照
- このbenchmark reportは証跡パックの一部であり、本番SLA・第三者認証・顧客環境測定ではない
