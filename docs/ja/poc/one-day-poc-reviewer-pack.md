# One-Day VERITAS PoC Reviewer Pack（外部レビュアー向け）

> 英語版（`docs/en/poc/one-day-poc-reviewer-pack.md`）が正本です。日本語版は補助説明です。

## 1. 目的

このパックは、外部レビュアーが VERITAS の PoC 証跡を短時間で確認するための手順です。
用途はレビュー、デューデリジェンス、技術評価です。
**本番認証を示すものではありません。**

## 2. 想定読者

- HPAN レビュアー
- エンタープライズ AI ガバナンス担当
- セキュリティ / 監査担当
- 投資家 / 技術 DD 担当
- 連携パートナー

## 3. レビュアーが確認すべき点

- Observability capabilities endpoint を確認できること
- JSON 証跡パケットを生成できること
- Markdown 証跡パケットを生成できること
- 生成した証跡を self-validation できること
- 証跡 JSON が repo-local schema に準拠すること
- スクリプト実行前に sample evidence packet が参照できること
- API key / token / raw endpoint / raw env 値 / raw request-response body が証跡に書き出されないこと

## 4. 最小実行コマンド

以下のコマンドをそのまま使用してください。

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_smoke.py \
  --json \
  --evidence-json /tmp/veritas_poc_evidence.json \
  --evidence-md /tmp/veritas_poc_evidence.md \
  --validate-generated-evidence
```

## 5. 成功時の期待出力

以下の文字列を含むことを確認してください。

- `Wrote sanitized evidence JSON: ...`
- `Generated evidence validation: VALID one_day_poc_evidence.v1`
- `Wrote sanitized evidence Markdown: ...`
- `ok` と `capabilities_ok` を含む JSON summary
- `--json` を使う場合は stdout を JSON として parse し、status line は stderr 側を確認してください。

stdout 全体の厳密な行順までは固定要件にしないでください（成功シグナルの有無を確認）。

## 6. 任意: オフライン検証コマンド

```bash
python scripts/demo/one_day_poc_smoke.py \
  --validate-evidence /tmp/veritas_poc_evidence.json
```

期待値:

- `VALID one_day_poc_evidence.v1`

## 7. 任意: スキーマパス確認コマンド

```bash
python scripts/demo/one_day_poc_smoke.py --print-schema-path
```

期待値:

- `schemas/poc/one_day_poc_evidence.v1.schema.json`

## 8. レビュアーが確認すべきファイル

- `/tmp/veritas_poc_evidence.json`
- `/tmp/veritas_poc_evidence.md`
- `schemas/poc/one_day_poc_evidence.v1.schema.json`
- `docs/en/poc/sample-one-day-poc-evidence.json`
- `docs/en/poc/sample-one-day-poc-evidence.md`
- `docs/ja/poc/sample-one-day-poc-evidence.md`
- `docs/en/poc/one-day-poc-walkthrough.md`
- `docs/ja/poc/one-day-poc-walkthrough.md`

## 9. 成功条件チェックリスト

- [ ] API server が起動している
- [ ] API key が `governance_read` ロール（例: `auditor` / `admin`）にマップされている
- [ ] Smoke script が完了する
- [ ] JSON evidence file が生成される
- [ ] Markdown evidence file が生成される
- [ ] generated evidence validation が `VALID` を返す
- [ ] offline validation が `VALID` を返す
- [ ] 証跡に API key が含まれない
- [ ] 証跡に raw exporter endpoint が含まれない
- [ ] 証跡に raw env 値が含まれない
- [ ] 証跡に raw request/response body がコピーされない
- [ ] `generated_at` が固定 UTC Z 形式 `YYYY-MM-DDTHH:MM:SSZ` である
- [ ] `non_goals` が存在する
- [ ] `limitations` を理解している

## 10. セキュリティ境界

- API key は書き出されません。
- Raw endpoint は書き出されません。
- Raw env 値は書き出されません。
- Raw request/response body はコピーされません。
- validation 出力に raw evidence body は表示されません。
- CLI validation は v1 schema に整合する stdlib ベースの軽量 contract check です。
- CLI validation は外部 `jsonschema` エンジンの完全実装ではありません。

## 11. 非目標 / 制約

- 本番認証ではありません。
- 最終的なエンタープライズ SLA ではありません。
- Jaeger / Grafana / Tempo / OTLP の導入は含みません。
- 暗号学的な human approval signature は含みません。
- 現行実装を超える TrustLog durability 保証は含みません。
- これ単体で live customer integration の証明にはなりません。


## 12. このレビューで証明しないこと

- 法的認証ではありません。
- 適合性評価ではありません。
- EU適合宣言（EU Declaration of Conformity）ではありません。
- CEマーキングではありません。
- 本番SLAの保証ではありません。
- 法務担当者・法律事務所レビューの代替ではありません。

## 13. レビューノート（推奨）

- 「評価すべき論点は、これがフルのエンタープライズ配備かどうかではなく、VERITAS が governed AI action flow に対して reviewable かつ sanitized で schema-aligned な証跡を出力できるかどうかである。」
- 「この PoC は、監査可能な decision-boundary の実証として評価すべきである。」
- 「本番ハードニングには、デプロイ構成、運用統制、保持ポリシー、ID 連携、顧客固有のリスク統制が必要となる。」


## 任意のパフォーマンスベンチマーク（Optional performance benchmark）

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py \
  --runs 10 \
  --warmup 2 \
  --json \
  --out-json runtime/dev/benchmarks/veritas_poc_benchmark.json \
  --out-md runtime/dev/benchmarks/veritas_poc_benchmark.md
```

生成された `runtime/dev/benchmarks/veritas_poc_benchmark.json` と `runtime/dev/benchmarks/veritas_poc_benchmark.md` をレビュアー向け提出物に含めてください。

## 14. トラブルシューティング

- API key がない: `VERITAS_API_KEY` を設定して再実行。
- `401` / `403`: キーの有効性とロールマッピング（`governance_read`、例: `auditor` / `admin`）を確認。
- `capabilities_ok: false`: API server の稼働状態と capabilities endpoint の可用性を確認。
- Evidence validation invalid: 再生成し、v1 schema path と JSON shape の整合を確認。
- 書き込み失敗: 出力先（例: `/tmp`）の書き込み権限を確認。
- `generated_at` invalid: `YYYY-MM-DDTHH:MM:SSZ` 形式を確認。
- Schema path not found: リポジトリに `schemas/poc/one_day_poc_evidence.v1.schema.json` が存在するか確認。

## 15. PoC 後に送付すべきもの

- 生成された JSON evidence packet
- 生成された Markdown evidence packet
- 実行コマンド
- 可能であれば VERITAS の commit hash または release tag
- レビューノート
- 既知の制約


## Provider依存に関する注意

- 現時点で runtime path の production-tier provider は OpenAI です。
- provider tier と制約は `docs/ja/operations/provider-support-matrix.md` を参照してください。
- このPoCのみから、on-prem/private cloud/multi-provider の本番対応を推論しないでください。
