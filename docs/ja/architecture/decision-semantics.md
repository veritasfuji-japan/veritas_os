# Decision Semantics（Phase-1 共通契約）

本書は Phase-1 の **decision semantics 正本仕様** です。

## Current behavior

本仕様は `veritas_os/core/pipeline/pipeline_response.py::_derive_business_fields` の現挙動を文書化したものです。ランタイム挙動の変更は目的としません。

## Legacy / alias values

`gate_decision` は後方互換のため canonical 値と legacy/alias 値を併存で受け付けます。

## Future tightening candidates

- `gate_decision` を canonical 値（`proceed|hold|block|human_review_required`）へ段階的収束。
- `allow|deny|modify|rejected|abstain|unknown` は入力互換レイヤでのみ許容。
- 禁則組み合わせを schema レベルで強制。

## A. gate_decision 正式 semantics

| 値 | current meaning | primary intent | UI 期待ラベル | legacy/alias | 推奨 | 他値との関係 | 優先レベル |
|---|---|---|---|---|---|---|---|
| `proceed` | 実行継続可能 | 通常実行 | Proceed | いいえ | 推奨 | canonical の肯定ゲート | 最低 |
| `hold` | 即時実行せず保留 | 証拠/統制の補完 | Hold | いいえ | 推奨 | canonical の保留 | 中 |
| `block` | fail-closed で停止 | 実行拒否 | Blocked | いいえ | 推奨 | canonical の拒否 | 最上位 |
| `human_review_required` | 人手審査境界へエスカレーション | 人手判定へのハンドオフ | Human review required | いいえ | 推奨 | canonical の審査要求 | 高 |
| `allow` | 旧 FUJI の許可系入力 | 後方互換 | response generation allowed | はい | 限定 | 通常は `proceed` 系へ正規化 | 低 |
| `deny` | 旧拒否系入力 | 後方互換 | Blocked by gate | はい | 限定 | `block` に正規化 | 高 |
| `modify` | 旧修正付き許可 | 後方互換 | Gate hold | はい | 限定 | `hold` 系へ寄る | 中 |
| `rejected` | 旧拒否 alias | 後方互換 | Blocked by gate | はい | 限定 | `block` 同等 | 高 |
| `abstain` | 旧保留/回答回避 | 後方互換 | Gate hold | はい | 限定 | `hold` 系として扱う | 中 |
| `unknown` | 欠損時 fallback | 防御的デフォルト | Gate status | はい | 原則非推奨 | stop reasons で再分類される | 最低 |

### 重要な明示

- `allow` と `proceed` は同義ではありません。`allow` は legacy 入力互換、`proceed` は canonical 出力です。
- `block` / `deny` / `rejected` は拒否系で、公開契約は `block` を正本とします。
- `human_review_required` は **gate 値** であり、同名 boolean flag と並行して保持します。

## B. business_decision 正式 semantics

| 値 | 意味 | 利用タイミング | gate との組み合わせ |
|---|---|---|---|
| `APPROVE` | 案件ライフサイクル上で承認可能 | stop reason なし | 通常 `proceed` |
| `DENY` | 案件拒否 | fail-closed 停止 | `block` |
| `HOLD` | 案件保留 | 統制/証跡/ルール準備不足 | 通常 `hold` |
| `REVIEW_REQUIRED` | 人手審査必須 | 境界曖昧/審査フラグ | `human_review_required` |
| `POLICY_DEFINITION_REQUIRED` | ポリシー定義不足 | policy 定義要求理由が明示 | 多くは `hold` |
| `EVIDENCE_REQUIRED` | 証拠不足 | missing_evidence が存在 | 多くは `hold` |

## C. gate × business の禁則/許容

| 組み合わせ | 判定 |
|---|---|
| `gate=block` + `business=APPROVE` | 不可 |
| `gate=hold` + `business=APPROVE` | 不可 |
| `gate=human_review_required` + `human_review_required=false` | 不可 |
| `gate=proceed` + `business=DENY` | 不可 |
| `gate=proceed` + `business=APPROVE` | 許容 |
| `gate=hold` + `business=HOLD` | 許容 |
| `gate=hold` + `business=EVIDENCE_REQUIRED` | 許容 |
| `gate=human_review_required` + `business=REVIEW_REQUIRED` | 許容 |
| legacy gate 値 + canonical business 値 | 非推奨だが現状許容 |

## D. stop_reasons 優先順位（現実装）

`_derive_business_fields` の判定順（現挙動）:

1. `rollback_not_supported` → `block`
2. `irreversible_action` + `audit_trail_incomplete` → `block`
3. `secure_prod_controls_missing` → `block`
4. 拒否系入力（`deny/rejected/block`）→ `block`
5. `required_evidence_missing` → `hold`
6. `high_risk_ambiguity`（`risk_score >= 0.8`）→ `human_review_required`
7. `approval_boundary_unknown` または `human_review_required=true` → `human_review_required`
8. `rule_undefined` / `audit_trail_incomplete` / `secure_controls_missing` または `hold/modify/abstain` → `hold`
9. それ以外 → `proceed`

## E. human_review_required の位置づけ

- flag 意味: 実行前に人間の裁定が必要。
- gate との関係: true または境界曖昧時に `gate_decision=human_review_required` へ昇格。
- business との関係: 原則 `REVIEW_REQUIRED`。
- UI 解釈: gate 値を主表示し、flag を審査義務として補助表示する。

## F. decision_status との関係

- `decision_status` は legacy 互換のため残存。
- 公開契約は `gate_decision` / `business_decision` を優先。
- 旧クライアントの `decision_status`（`allow|modify|rejected|block|abstain`）を継続受理する。
