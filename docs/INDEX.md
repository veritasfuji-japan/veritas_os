# VERITAS OS Documentation Index

**English** | [日本語はこちら / Japanese below](#veritas-os-ドキュメント総合インデックス)

---

## Quick Navigation

| Category | English | 日本語 |
|----------|---------|--------|
| **Getting Started** | [README](../README.md) | [README_JP](../README_JP.md) |
| **User Manual** | — | [User Manual](ja/guides/user-manual.md) |
| **Operations** | [Operations](en/operations/) | [Operations](ja/operations/) |
| **Validation** | [Validation](en/validation/) | [Validation](ja/validation/) |
| **Governance** | [Governance](en/governance/) | [Governance](ja/governance/) |
| **Architecture** | [Architecture](architecture/) | — |
| **Bind Boundary (EN)** | [Bind-Boundary Governance](en/architecture/bind-boundary-governance-artifacts.md) | — |
| **EU AI Act** | [EU AI Act](eu_ai_act/) | [EU AI Act (JA)](ja/governance/) |
| **Guides** | [Guides](en/guides/) | [Guides](ja/guides/) |
| **Reviews (EN)** | [Reviews](en/reviews/) | — |
| **Reviews (JA)** | — | [Reviews](ja/reviews/) |
| **UI / Frontend** | [UI Docs](ui/) | — |
| **Benchmarks** | [Benchmarks](benchmarks/) | — |
| **Archive** | [Archive](archive/) | — |

## Documentation Hubs

- **English Hub**: [docs/en/README.md](en/README.md)
- **Japanese Hub / 日本語入口**: [docs/ja/README.md](ja/README.md)

## Key Resources

- [Documentation Map (bilingual correspondence)](DOCUMENTATION_MAP.md)
- [Bilingual Maintenance Rules](BILINGUAL_RULES.md)
- [Path Migration Table](PATH_MIGRATION.md)
- [金融 PoC パック（JA）](ja/guides/poc-pack-financial-quickstart.md)

## Directory Structure

```
docs/
├── INDEX.md                 ← You are here
├── DOCUMENTATION_MAP.md     ← Bilingual correspondence table
├── BILINGUAL_RULES.md       ← Rules for maintaining EN/JA docs
├── PATH_MIGRATION.md        ← Old path → new path mapping
│
├── en/                      ← English documentation
│   ├── README.md            ← English hub
│   ├── operations/          ← Runbooks, deployment, env config
│   ├── validation/          ← Testing, coverage, audit readiness
│   ├── governance/          ← Governance artifact lifecycle
│   ├── guides/              ← Demo script, migration guide
│   ├── reviews/             ← EN code reviews
│   └── notes/               ← Technical notes
│
├── ja/                      ← 日本語ドキュメント
│   ├── README.md            ← 日本語入口
│   ├── operations/          ← 運用ランブック
│   ├── validation/          ← テスト・カバレッジレポート
│   ├── governance/          ← ガバナンス・コンプライアンス
│   ├── guides/              ← ユーザーマニュアル、リファレンス
│   ├── reviews/             ← コードレビュー (65+ files)
│   ├── audits/              ← 監査レポート
│   └── notes/               ← 技術ノート
│
├── architecture/            ← Architecture ADRs & design notes (EN)
├── eu_ai_act/               ← EU AI Act compliance artifacts (EN)
├── ui/                      ← Frontend/UI documentation (mixed)
├── benchmarks/              ← Benchmark plans (EN)
├── papers/                  ← Academic papers (PDF)
├── press/                   ← Press releases (EN)
│
└── archive/                 ← Historical & dated documents
    ├── reviews/             ← Root-level dated reviews
    ├── notes/               ← Historical technical notes
    ├── reports/             ← Point-in-time reports
    └── operations/          ← Legacy operation docs
```

---

# VERITAS OS ドキュメント総合インデックス

[English above](#veritas-os-documentation-index) | **日本語**

---

## クイックナビゲーション

| カテゴリ | English | 日本語 |
|----------|---------|--------|
| **はじめに** | [README](../README.md) | [README_JP](../README_JP.md) |
| **ユーザーマニュアル** | — | [ユーザーマニュアル](ja/guides/user-manual.md) |
| **運用** | [Operations](en/operations/) | [運用](ja/operations/) |
| **検証** | [Validation](en/validation/) | [検証](ja/validation/) |
| **ガバナンス** | [Governance](en/governance/) | [ガバナンス](ja/governance/) |
| **アーキテクチャ** | [Architecture](architecture/) | — |
| **EU AI Act** | [EU AI Act](eu_ai_act/) | [EU AI Act (JA)](ja/governance/) |
| **ガイド** | [Guides](en/guides/) | [ガイド](ja/guides/) |
| **レビュー (EN)** | [Reviews](en/reviews/) | — |
| **レビュー (JA)** | — | [レビュー](ja/reviews/) |
| **UI** | [UI Docs](ui/) | — |
| **ベンチマーク** | [Benchmarks](benchmarks/) | — |
| **アーカイブ** | [Archive](archive/) | — |

## ドキュメントハブ

- **English Hub**: [docs/en/README.md](en/README.md)
- **日本語入口**: [docs/ja/README.md](ja/README.md)

## 主要リソース

- [ドキュメント対応表（英日対応）](DOCUMENTATION_MAP.md)
- [バイリンガル運用ルール](BILINGUAL_RULES.md)
- [パス移行表](PATH_MIGRATION.md)

## 言語対応ポリシー

各文書は以下の3種類に分類されています。詳細は [BILINGUAL_RULES.md](BILINGUAL_RULES.md) を参照してください。

- **Type A**: 英日両方を維持（README, ユーザーマニュアル, 主要運用ガイド）
- **Type B**: 英語正本のみ（技術仕様, アーキテクチャ, ベンチマーク）
- **Type C**: 日本語のみ（日本語固有のレビュー, 監査, コミュニティ向け資料）
