# Decision Semantics（日本語解説）

## 位置づけ
この文書は、意思決定結果と bind フェーズ結果の公開契約を確認するための日本語解説です。対象読者は、運用者・監査担当・実装担当です。

## 要点
- Decision Governance / 意思決定ガバナンス では、`decision` と `bind` を別フェーズで扱います。
- operator-facing governance surface / 運用者向けガバナンス面 では、`bind_summary` を最小表示語彙として扱います。
- 詳細証跡は `BindReceipt` / bind証跡 に連結され、Replay / 再現実行と監査で追跡できます。

## VERITASにおける意味
- FUJI Gate は bind 境界で fail-closed / 安全側停止 の最終判定点になります。
- TrustLog と `governance_identity` / ガバナンス識別子 を合わせることで、意思決定から副作用までの系譜を監査可能にします。
- Mission Control は `bind_summary` / bind概要 と `BindReceipt` を併用して、運用 triage と証跡確認を分離します。


## 判断ソース間の制限的優先順位

VERITAS では、複数の判断ソースが食い違う場合、**より制限的な判断が優先されます**。
あるコンポーネントの permissive decision（許可的判断）は、別コンポーネントの restrictive decision（制限的判断）を上書きできません。
特に、FUJI が `deny` / `rejected` / `block` 相当の判断を返した場合、downstream bind/commit systems はそれを advisory（参考情報）として扱ってはなりません。

| 優先度 | 意味 | 代表的な語彙 | bind/commit での扱い |
|---|---|---|---|
| 3 | 拒否 / 実行ブロック | `deny`, `rejected`, `block` | commit 不可（block） |
| 2 | 保留 / 人間レビュー・エスカレーション必須 | `hold`, `review`, `escalate`, `human_review_required` | silent allow 禁止（escalate / review） |
| 1 | 許可 / 実行可能候補 | `allow`, `approved`, `approve`, `proceed` | 他に制限的判断がない場合のみ bind 候補 |

実効判断は、gate、policy、business、FUJI、bind-time checks の全体から最も制限的な判断として解決されます。
そのため、`gate_decision=allow` や `business_decision=APPROVE` が存在しても、FUJI 側に `rejected` / `deny` があれば、bind/commit は fail-closed で停止します。
未知または malformed な判断文字列も、実行境界では安全側（block）に倒す必要があります。

## 実装上の確認ポイント
- `/v1/decide` とガバナンス mutation API の bind 公開フィールドが整合しているか。
- `/v1/governance/bind-receipts`（list/export/detail）で `BindReceipt` を再取得できるか。
- スキーマ変更時は Replay と API 契約テストを併せて確認すること。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- ベータ段階のため、全 effect path が bind-governed / bind統制対象 とまでは主張しません。
- 本番導入には環境別の鍵管理、監査設計、運用審査が必要です。

## 英語正本
- [docs/en/architecture/decision-semantics.md](../../en/architecture/decision-semantics.md)
