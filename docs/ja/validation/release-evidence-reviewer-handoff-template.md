# リリース証跡レビュー引き渡しテンプレート

この文書は、[`docs/en/validation/release-evidence-reviewer-handoff-template.md`](../../en/validation/release-evidence-reviewer-handoff-template.md) の日本語説明ページです。外部レビュアー、企業評価者、技術 DD チーム向けに、release evidence / staged readiness review の提出フォーマットの目的と読み方を整理します。

## 英語正本

- [`docs/en/validation/release-evidence-reviewer-handoff-template.md`](../../en/validation/release-evidence-reviewer-handoff-template.md)

## 目的

- release evidence と staged readiness review を、レビュアーへ引き渡す際の提出フォーマットを明確化する。
- 何を実行したか、どの証跡を提出したか、何が未解決かを整理する。
- 過大な主張を避け、非主張境界を明示する。

## 使い方

1. 英語正本テンプレートに沿って、実行コマンド・証跡・結果を記入します。
2. `deployment_ready` の値だけで判断せず、compose/live subreport の添付有無を確認します。
3. advisory findings と未解決事項を記録し、レビュアー判断に必要な補足を残します。
4. 必要に応じて redaction 方針と実行環境（local / CI / staging / customer-managed）を追記します。
5. `make prepare-release-evidence-handoff` を実行すると、英語正本テンプレートを `release-artifacts/release-evidence-reviewer-handoff.md` にコピーできます。
6. `release-artifacts/release-evidence-reviewer-handoff.md` を、staged readiness report などの生成済み証跡と一緒に記入・提出します。

## 提出する主な証跡

- `release-artifacts/staged-readiness-report.json`
- `release-artifacts/staged-readiness-report.txt`
- `release-artifacts/compose-validation-report.json`（compose subreport を添付した場合）
- `release-artifacts/live-provider-report.json`（live provider subreport を添付した場合）
- 実行コマンドログ、CI 状態、PR URL、レビューノート

## `deployment_ready` の読み方

- `deployment_ready=true` は、blocking governance checks が通り、添付済み compose report に失敗がないことを示します。
- これは本番認証ではない、または認証ではないという境界を前提に解釈します。
- `deployment_ready=true` でも、compose validation が未添付なら compose 実行の証跡にはなりません。
- `deployment_ready=true` でも、live provider validation が未添付なら live provider 実行の証跡にはなりません。

## compose/live subreport の確認

- compose/live subreport が添付済みか未添付かを明示して確認してください。
- 未添付は、compose/live validation が走った証拠ではありません。
- live provider validation は provider secrets が必要になる場合があります。
- provider secrets が未設定の場合、live provider checks が skip される場合があります。

## 非主張境界

- この引き渡しは法的・規制上・コンプライアンス上の認証を意味しません。
- 顧客環境で実行・記録されていない限り、顧客環境検証ではないと扱います。
- 第三者認証を主張しません。
- 本番運用可否の最終判断を代替する資料として扱いません。

## 関連文書

- [`docs/en/validation/release-evidence-reviewer-handoff-template.md`](../../en/validation/release-evidence-reviewer-handoff-template.md)
- [`docs/REVIEWER_ENTRYPOINT.md`](../../REVIEWER_ENTRYPOINT.md)
- [`docs/en/operations/operational-readiness-runbook.md`](../../en/operations/operational-readiness-runbook.md)
- [`docs/en/validation/production-validation.md`](../../en/validation/production-validation.md)
- [`docs/ja/validation/production-validation.md`](production-validation.md)
