# Policy-as-Code (Stage 1)

## 目的

本ドキュメントは、VERITAS の Policy-as-Code 第1段階として導入した
**source policy schema / validation / canonical IR / semantic hash** の最小実装を説明します。

## Source Policy Format

- Authoring 形式: YAML または JSON
- スキーマバージョン: `schema_version: "1.0"`
- 必須項目:
  - `policy_id`
  - `version`
  - `title`
  - `description`
  - `scope` (`domains` / `routes` / `actors`)
  - `outcome` (`decision` / `reason`)
- 任意項目:
  - `conditions`
  - `requirements`
  - `constraints`
  - `obligations`
  - `test_vectors`

許可される `outcome.decision` は次の列挙のみです。

- `allow`
- `deny`
- `halt`
- `escalate`
- `require_human_review`

## Validation Flow

1. `veritas_os.policy.schema.load_and_validate_policy` がファイル拡張子を検証します。
2. YAML/JSON をロードし、マッピング形式であることを検証します。
3. `SourcePolicy` (Pydantic strict model) で以下を検証します。
   - 必須フィールド
   - 列挙値 (`outcome`, 演算子)
   - ネスト構造 (`scope`, `requirements`, `outcome`)
   - `minimum_approval_count` と `required_reviewers` の整合性
4. エラー時は `PolicyValidationError` を返します。

## Canonical IR の役割

`veritas_os.policy.normalize.to_canonical_ir` は、監査と差分比較のための安定化処理を提供します。

- リスト値を重複排除 + ソート
- 条件/制約を deterministic order に整列
- test vector も安定ソート
- 不要な見た目差分（記述順序）を除去

この Canonical IR を `veritas_os.policy.hash.semantic_policy_hash` に入力して、
見た目に依存しない semantic hash (SHA-256) を生成します。

## Example Policies

- `policies/examples/high_risk_route_requires_human_review.yaml`
- `policies/examples/external_tool_usage_denied.yaml`
- `policies/examples/missing_mandatory_evidence_halt.yaml`

## この Task で未実装

- FUJI runtime への本格統合
- Policy compiler (`Policy -> ValueCore/FUJI rules`) 本体
- generated tests の自動生成
- bundle signing / distribution
- UI 差分可視化

## セキュリティ上の注意

- 本段階の semantic hash は **整合性検証の基礎** であり、署名・鍵管理は未導入です。
- そのため、本番供給チェーンでは将来タスクとして署名検証を追加してください。
