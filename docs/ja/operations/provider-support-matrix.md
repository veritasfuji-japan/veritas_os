# Provider Support Matrix（モデル提供者対応マトリクス）

> 英語版（`docs/en/operations/provider-support-matrix.md`）が正本です。日本語版は補助説明です。

## 目的

本ドキュメントは、VERITAS OS の model provider 対応tierを明確化し、enterprise reviewer / investor / customer が provider 依存境界を誤解なく評価できるようにするものです。

## Provider依存に関する位置づけ

VERITASはprovider抽象化境界を持つ設計ですが、現時点でproduction-tierとして扱うproviderは、本マトリクスで明示されたものに限られます。plannedまたはexperimentalのproviderは、追加検証なしに規制対象ワークフロー、外部顧客デモ、企業調達審査でproduction対応として扱うべきではありません。

Provider supportは、そのproviderが利用組織のデータ所在、セキュリティ、調達、法務、規制要件を満たすことを意味しません。利用組織は、providerの利用規約、データ処理、保存、所在地、モデル挙動、リスク管理を個別に確認する必要があります。

## 現在のsupport tier

support tier は `veritas_os/core/llm_client.py` の `PROVIDER_SUPPORT_TIER` に基づきます。

## “production” の意味

production support は、少なくとも次を意味します。

- 構成手順が文書化されていること
- 既存のテストまたは smoke path で該当経路が確認されていること（該当範囲）
- 現行 runtime client surface で利用可能であること
- 既知の失敗挙動が定義されていること

一方で、production support は次を意味しません。

- すべての顧客に対する法的承認
- データ所在地要件の充足保証
- on-prem/private cloud 対応保証
- 規制用途の導入認証
- provider 間のモデル挙動同等性

## “planned” の意味

planned は、将来的な対応経路を示しますが、現時点で production-ready を意味しません。

## “experimental” の意味

experimental は、開発者検証やアダプタ検討向けの段階であり、安定性保証や production SLA 対象ではありません。

## 現在のprovider matrix

| Provider | Tier | Current status | Intended use | Known limitations |
|---|---|---|---|---|
| OpenAI | Production | Default supported provider | Current PoC / runtime path | 有効な認証情報と組織側のproviderポリシーレビューが必要 |
| Anthropic | Planned | Not production-supported yet | Future provider adapter | 現行のgoverned decision pathで未検証 |
| Google | Planned | Not production-supported yet | Future provider adapter | 現行のgoverned decision pathで未検証 |
| Ollama / local models | Experimental | Local/experimental adapter only | Developer experiments / local evaluation | production SLA対象外、規制対象ワークフロー未検証 |
| OpenRouter / compatible gateway | Experimental | Gateway-dependent adapter path | Provider abstraction experiments | gateway挙動・データ処理・遅延特性の個別レビューが必要 |

## 既知の制約

- 現時点のproduction-tier providerはOpenAIのみです。
- support tier は法務/コンプライアンス承認を意味しません。
- 抽象化インターフェースの存在だけでは multi-provider parity を保証しません。
