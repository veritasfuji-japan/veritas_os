# 直近のハードニング整理

この文書は、監査性・観測性・CI品質ゲート・API互換性・依存関係リスク可視化に関する直近の強化内容を整理します。

## 対象範囲

これらの変更は、VERITAS OS の中核的なガバナンス契約を変えずに、運用上の信頼性向上を支援するものです。

## 強化内容

### 監査性
- RBAC拒否イベントを privacy-safe な signed audit event として TrustLog に記録するようにしました。
- RBAC拒否に必要なフィールドを、compact signed TrustLog summary 後にも保持するようにしました。

### 観測性
- trace correlation 付きの structured JSON logging を有効化できるようにしました。
- request trace ID を API middleware と logs に伝搬し、横断的な追跡をしやすくしました。

### 品質ゲート
- replay report check に strict mode と `--require-reports` を追加し、必要な証跡が欠ける場合は fail closed できるようにしました。
- pytest discovery で `veritas_os/tests` と top-level `tests` の両方を明示しました。

### API信頼性
- `/v1/decide` response coercion で、nested bind data 由来の bind compatibility fields を保持するようにしました。
- OpenAPI generation で、既知の third-party Pydantic deprecation warning に対する guard を追加しました。

### 依存関係リスクの可視化
- FastAPI/Pydantic の将来互換性を確認する non-blocking CI lane を追加しました。
- compatibility lane の resolved versions / targeted tests / pytest result / exit code を GitHub Actions summary に表示するようにしました。

## この文書が主張しないこと

- すべての将来の FastAPI/Pydantic version との互換性を保証するものではありません。
- future dependency lane を blocking gate に変更するものではありません。
- production dependency pins を変更するものではありません。
- 外部の security/compliance review を置き換えるものではありません。

## レビューチェックリスト

今後の変更では以下を確認してください。
- audit event は privacy-safe か
- required evidence が欠けた場合に quality gate は fail closed するか
- CI lane は blocking / non-blocking の区別が明確か
- production pins を変えずに dependency-risk signal を確認できるか
