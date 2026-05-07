# One-Day PoC パフォーマンスベンチマークレポート

> 英語版（`docs/en/poc/one-day-poc-performance-report.md`）が正本です。日本語版は補助説明です。

## 目的

本ドキュメントは、One-Day PoC の主要導線について、再現可能なローカル遅延計測証跡を取得する手順を示します。

## 実行方法

推奨コマンド:

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py \
  --runs 10 \
  --warmup 2 \
  --json \
  --out-json /tmp/veritas_poc_benchmark.json \
  --out-md /tmp/veritas_poc_benchmark.md
```

## JSON出力項目

`one_day_poc_benchmark.v1` 形式で、以下を出力します。

- scenario / measured_at
- runs / warmup / timeout
- sanitize 済み環境情報
- 遅延サマリ（min/p50/p95/p99/max/mean/stdev）
- ターゲットごとの success/failure
- 制約事項と sanitize 済み failure 情報

## Markdown出力

`--out-md` により以下を含むレポートを生成します。

- Summary
- Environment
- Benchmark Results
- Methodology
- Limitations
- What this does not prove
- Recommended next measurements

## レビュアー向け解釈

- **ローカルベンチマーク証跡**として扱ってください。
- 本番性能やSLAの確約ではありません。
- 同一環境で複数回実行し、傾向確認に利用してください。

## 制約

- ローカル環境差分の影響を受けます。
- ネットワーク/モデル提供者/構成で結果は変動します。
- 負荷・同時実行・長時間安定性試験は含みません。

## 本番SLAではない

本結果は本番SLAを示しません。

## 法的認証ではない

本結果はEU AI法準拠の法的認証を示しません。

## 次の本番向け計測

- ステージング環境の基準値作成
- 同時実行・スループット計測
- tail latency の計測
- リージョン/ネットワーク差分計測
