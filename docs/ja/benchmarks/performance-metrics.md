# 性能メトリクス

英語版が正本であり、日本語版は補助説明です。

## 英語正本

- [Performance Metrics](../../en/benchmarks/performance-metrics.md)

本資料は、VERITAS OS における性能測定の入口として、再現可能な deterministic local harness を定義します。

- deterministic local harness である
- 外部LLM/APIは呼ばない
- 本番E2Eレイテンシではない
- cloud deployment latencyではない
- 本番SLAではない
- 第三者認証済みではない
- ビジネス向け数値を出す前に、測定方法を再現可能にするための資料である

- p95_ms / p99_ms は測定iterationの nearest-rank percentile であり、本番レイテンシ保証ではありません。


## 最新ローカルartifact

- 最新のlocal deterministic artifact:
  - `docs/en/benchmarks/local-performance-metrics.latest.json`
  - `docs/en/benchmarks/local-performance-metrics.latest.md`
- 日本語補助:
  - `docs/ja/benchmarks/local-performance-metrics.latest.md`
- 本番SLAではない
- 顧客環境測定ではない
