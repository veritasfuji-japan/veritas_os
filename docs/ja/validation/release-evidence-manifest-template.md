# リリース証跡マニフェストテンプレート

この文書は `docs/en/validation/release-evidence-manifest-template.md` の日本語説明ページです。

## 英語正本

- [`docs/en/validation/release-evidence-manifest-template.md`](../../en/validation/release-evidence-manifest-template.md)

## 目的

- manifest はリリース証跡パッケージの索引です。
- 提出物の存在/未存在、必須/条件付き項目、確認境界を 1 枚で共有します。
- 本番認証ではない境界を明示します。

## 使い方

1. `make prepare-release-evidence-manifest` を実行し、`release-artifacts/release-evidence-manifest.md` を準備します。
2. `make prepare-release-evidence-handoff` を実行し、`release-artifacts/release-evidence-reviewer-handoff.md` を準備します。
3. `make prepare-release-evidence-checksums` で `release-artifacts/release-evidence-checksums.sha256` を生成します。
4. `make prepare-release-evidence-package` を使うと、サブレポートなしのリリース証跡パッケージを 1 コマンドで準備できます。
5. manifest で提出物の索引を埋め、handoff file で reviewer-facing interpretation / acknowledgement を記録します。

## 主な提出物

- `release-artifacts/release-evidence-manifest.md`
- `release-artifacts/release-evidence-reviewer-handoff.md`
- `release-artifacts/staged-readiness-report.json`
- `release-artifacts/staged-readiness-report.txt`
- `release-artifacts/compose-validation-report.json`
- `release-artifacts/live-provider-report.json`
- `release-artifacts/release-evidence-checksums.sha256`

## compose/live artifact の確認

- compose/live artifact が未添付の場合、それは検証が走った証拠ではありません。
- 顧客環境で実行・記録されていない限り、顧客環境検証ではない扱いです。

## reviewer handoff file との違い

- manifest は提出パッケージの索引です。
- handoff file は reviewer-facing interpretation / acknowledgement の記録です。

## 非主張境界

- 本番認証ではない。
- 第三者認証ではない。
- checksum は提出ファイルの変更確認を助けるが、それ自体は第三者証明ではない。
- checksum は提出ファイルの変更確認を助けるが、それ自体は改ざん不能保管ではない。
- 顧客環境で実行・記録されていない限り、顧客環境検証ではない。

## 関連文書

- [`docs/en/validation/release-evidence-manifest-template.md`](../../en/validation/release-evidence-manifest-template.md)
- [`docs/en/validation/release-evidence-reviewer-handoff-template.md`](../../en/validation/release-evidence-reviewer-handoff-template.md)
- [`docs/REVIEWER_ENTRYPOINT.md`](../../REVIEWER_ENTRYPOINT.md)
- [`docs/en/operations/operational-readiness-runbook.md`](../../en/operations/operational-readiness-runbook.md)
- [`docs/ja/validation/release-evidence-reviewer-handoff-template.md`](release-evidence-reviewer-handoff-template.md)
