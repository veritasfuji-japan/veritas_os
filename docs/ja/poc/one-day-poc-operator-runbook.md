# One-Day PoC運用Runbook

- 英語版が正本であり、日本語版は補助説明です。
- これはOne-Day PoCを実施するoperator向けrunbookである。
- PoCの準備、実行、証跡収集、整理、レビュー担当者への引き渡し方法を説明する。
- One-Day PoC証跡パックを補完する。
- 本番デプロイ手順ではない。
- 本番SLAではない。
- 第三者認証ではない。
- 顧客環境測定ではない。
- EU AI Act準拠を認証するものではない。
- 外部LLM/provider latencyやcostは、明示的にproviderを有効化して別途記録しない限り測定対象ではない。

## 英語正本

- [One-Day PoC Operator Runbook](../../en/poc/one-day-poc-operator-runbook.md)

## Purpose

- One-Day PoCを実施するための再現可能な手順をoperatorに提供する。
- 顧客・投資家・技術レビュー担当者が確認できる形で成果物を整理する。
- PoCの主張をlocal/configured証跡の範囲に限定する。

## Operator responsibilities

- commit SHA、日時、operator名または役割、環境メモを記録する。
- 明示的に記録したredaction以外、収集後に生成証跡を編集しない。
- 必要に応じてraw成果物とsanitized成果物を分離する。
- レビュー時に非主張境界を明確に伝える。

## Pre-flight checklist

- [ ] 意図したcommitでリポジトリをcheckoutしている。
- [ ] 既存セットアップdocsに従って依存関係を導入済み。
- [ ] HTTP PoCフローを実行する場合、VERITAS API serverが利用可能。
- [ ] 必要箇所で`VERITAS_API_KEY`を設定済み。
- [ ] 出力ディレクトリを作成済み。
- [ ] 本番SLA / 認証 / 顧客環境測定の主張を行わない。
- [ ] 外部providerを有効化する場合、設定内容と測定範囲を別途記録する。

## Recommended evidence folder layout

```text
poc-evidence/
  README.md
  environment.md
  commands.md
  screenshots/
  json/
  markdown/
  logs/
  redactions.md
  reviewer-notes.md
```

- `environment.md`: 日付、commit SHA、local/configured環境メモ。
- `commands.md`: 実行したコマンドを正確に記録。
- `screenshots/`: block/allow decision pathのスクリーンショット。
- `json/`: 機械可読出力。
- `markdown/`: 人間可読レポート。
- `logs/`: 任意のローカルログ。
- `redactions.md`: 何をなぜマスクしたか。
- `reviewer-notes.md`: 引き渡し用サマリー。

## Run sequence

1. 環境情報とcommit SHAを記録する。
2. 必要に応じてVERITAS API serverの起動または稼働確認を行う。
3. 既存docs/scriptsを用いてOne-Day PoC walkthroughまたはsmoke flowを実行する。
4. local/configured HTTP benchmarkを対象とする場合のみ、One-Day PoC benchmarkを任意実行する。
5. JSON / Markdown / スクリーンショットを収集する。
6. 失敗と例外を記録する。
7. 必要に応じて機微情報をredactする。
8. reviewer向けhandoffパッケージを作成する。

具体コマンドは本runbookで新設せず、既存のwalkthrough/benchmark文書に従う。

## Evidence collection checklist

| Evidence | Required? | Where to save | Notes |
|---|---|---|---|
| Commit SHA and environment notes | Yes | `environment.md` | タイムスタンプとlocal/configured範囲を含める。 |
| Commands run | Yes | `commands.md` | 実行順を維持して正確に記録する。 |
| Blocked decision screenshot | Yes | `screenshots/` | シナリオ文脈と決定結果が分かる状態にする。 |
| Allowed decision screenshot if scenario exists | Conditional | `screenshots/` | allow経路が対象シナリオの場合のみ収集。 |
| JSON evidence packet if generated | Conditional | `json/` | 生成されたraw出力を保存する。 |
| Markdown evidence report if generated | Conditional | `markdown/` | reviewer可読の要約をJSONと対応させる。 |
| Local deterministic metrics artifact reference | Recommended | `reviewer-notes.md` | レビューで参照したdeterministic metricsを記載。 |
| One-Day PoC benchmark output if run | Conditional | `markdown/` or `json/` | benchmarkを実施した場合のみ記録。 |
| Redaction notes | Conditional | `redactions.md` | redaction対象と理由を明記。 |
| Reviewer notes | Yes | `reviewer-notes.md` | 結果、境界、フォローアップを要約。 |

## What to record for each run

- Date/time。
- Commit SHA。
- Operator role。
- Environment type: local / configured / customer-managed if applicable。
- Whether external providers were enabled。
- Commands run。
- Scenario names。
- Result: pass / fail / inconclusive。
- Exceptions or known limitations。

## Review handoff package

- reviewer向けの短いREADME。
- Evidence Packへのリンク。
- Operator Runbookへのリンク。
- Evidence folder。
- 既知の制約事項。
- 明示的な非主張境界。
- 未解決事項 / follow-up項目。

## Common failure modes

- 必要なAPI serverが起動していない。
- `VERITAS_API_KEY`が未設定。
- 証跡は生成されたがhandoff資料から参照されていない。
- local deterministic metricsを本番レイテンシと誤認する。
- provider測定なしでprovider cost/latencyを示唆する。
- スクリーンショットに文脈がない。
- redaction記録がない。
- reviewerがactionのblock/allow理由を特定できない。

## Non-claim boundaries

- local/configured PoC出力から本番SLAを主張しない。
- 第三者認証を主張しない。
- 実際にその環境で実行・記録した場合を除き、顧客環境測定を主張しない。
- EU AI Act準拠認証を主張しない。
- providerを明示的に有効化して別途測定しない限り、provider cost/latencyを主張しない。
- デモ用スクリーンショットを本番監査証跡として提示しない。

## Related documents

- [`docs/ja/poc/one-day-poc-evidence-pack.md`](one-day-poc-evidence-pack.md)
- [`docs/ja/poc/one-day-poc-reviewer-pack.md`](one-day-poc-reviewer-pack.md)
- [`docs/ja/poc/one-day-poc-walkthrough.md`](one-day-poc-walkthrough.md)
- [`docs/ja/poc/one-day-poc-performance-report.md`](one-day-poc-performance-report.md)
- [`docs/en/benchmarks/local-performance-metrics.latest.md`](../../en/benchmarks/local-performance-metrics.latest.md)
- [`docs/en/benchmarks/performance-metrics.md`](../../en/benchmarks/performance-metrics.md)
- [`docs/INDEX.md`](../../INDEX.md)
- [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md)
