# VERITAS OS 公開ポジショニングガイド（日本語）

## 公式の公開ポジション

**VERITAS OS = Decision Governance and Bind-Boundary Control Plane for AI Agents**

コアメッセージ:

- AIの意思決定を、現実世界に作用する前に **reviewable / traceable / replayable / auditable / enforceable** にする。
- VERITAS OS は **governance layer before execution** であり、実行ランタイムそのものとは役割が異なる。
- bind の公開契約として、`bind_outcome` / `bind_failure_reason` / `bind_reason_code` / `execution_intent_id` / `bind_receipt_id` を運用側で扱える。

## VERITAS OS が「あるもの / ないもの」

- **あるもの:** 企業・規制領域のワークフローで意思決定統制を担うガバナンス中心のOS層。
- **ないもの:** すべてのオーケストレーション/ランタイムを置換する基盤、または投機的AGI物語を前面に出す製品。

## 現時点の事実 / 将来方向

### 現時点の事実（実装済み）

- bind-boundary は少なくとも次の2つの運用経路で実装済み:
  1. `PUT /v1/governance/policy`（governance policy update path）
  2. `POST /v1/governance/policy-bundles/promote`（policy bundle promotion path）
- `GET /v1/governance/bind-receipts` と
  `GET /v1/governance/bind-receipts/{bind_receipt_id}` でレシート系譜を取得可能。
- replay/revalidation helper により、receipt は replayable governance artifact に近づいている。

### 将来方向（未完了）

- bind-boundary の適用範囲を追加の effect path へ拡張する。
- 複数 effect path を一貫統治する標準枠組みへ収束させる。
- これは方向性であり、現時点で全 effect path 完了を主張しない。

## 推奨表現

- Decision Governance OS
- governance layer before execution
- reviewable / traceable / replayable / auditable / enforceable
- fail-closed safety gate
- tamper-evident TrustLog lineage
- decision -> execution_intent -> bind_receipt lineage
- operator-facing governance surface
- bind outcome public contract

## 注意表現（限定利用）

以下は歴史的・研究的文脈を明示した場合に限定:

- Proto-AGI
- AGI framework
- self-improvement OS

タイトル・サブタイトル・冒頭説明段落での無注釈利用は禁止。

## Technical Maturity Snapshot（内部自己評価）

> このセクションは **internal re-evaluation / self-assessment（内部再評価）** であり、第三者認証ではありません。

| カテゴリ | 2026-03-15 | 2026-04-15 | 変動 |
|---|---|---|---|
| Architecture | 82 | 85 | +3 |
| Code Quality | 83 | 84 | +1 |
| Security | 80 | 86 | +6 |
| Testing | 88 | 89 | +1 |
| Production Readiness | 80 | 85 | +5 |
| Governance | 82 | 86 | +4 |
| Docs | 80 | 83 | +3 |
| Differentiation | 84 | 86 | +2 |
| **Overall** | **82** | **85 / 100** | **+3** |

基準レビュー:
- `docs/ja/reviews/technical_dd_review_ja_20260315.md`

## README要約方針（冒頭3〜5画面）

1. 何の製品か
2. 何を解決するか
3. runtime/orchestration との差分
4. regulated / enterprise 適合理由
5. 事実とロードマップの境界
