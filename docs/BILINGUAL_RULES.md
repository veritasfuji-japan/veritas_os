# Bilingual Documentation Maintenance Rules

# バイリンガルドキュメント運用ルール

---

## 1. Document Classification / 文書分類

All documents are classified into three types:

すべての文書を以下の3種類に分類します。

### Type A: EN + JA Both Maintained / 英日両方を維持

Documents important for both English and Japanese audiences.
Canonical version and translation are both maintained.

英語話者・日本語話者の両方にとって重要な文書。
正本と翻訳の両方を維持します。

**Current Type A documents / 現在の Type A 文書:**

| EN Path | JA Path | Notes |
|---------|---------|-------|
| `README.md` | `README_JP.md` | Fully paired |
| `docs/INDEX.md` | (bilingual in single file) | Single bilingual file |
| `docs/en/guides/migration-guide.md` | (bilingual in single file) | Single bilingual file |
| — | `docs/ja/guides/user-manual.md` | JA full; EN summary planned |

### Type B: EN Canonical Only / 英語正本のみ

Technical specifications, architecture docs, and operational runbooks
where English serves as the canonical technical reference.

英語が技術正本として機能する文書。

**Categories:**
- `docs/architecture/*`
- `docs/en/operations/*`
- `docs/en/validation/*`
- `docs/en/governance/*`
- `docs/eu_ai_act/*`
- `docs/ui/*`
- `docs/benchmarks/*`
- `docs/press/*`
- `docs/en/reviews/*`
- `docs/en/guides/demo-script.md`
- `docs/en/notes/*`

### Type C: JA Only / 日本語のみ

Documents targeting the Japanese community or created in Japanese
with no current need for English translation.

日本語コミュニティ向け、または日本語で作成され英訳の必要性が低い文書。

**Categories:**
- `docs/ja/reviews/*` (65+ code review files)
- `docs/ja/audits/*`
- `docs/ja/governance/*`
- `docs/ja/guides/fuji-error-codes.md`
- `docs/ja/guides/fuji-eu-enterprise-strict-usage.md`
- `docs/ja/guides/self-healing-loop.md`
- `docs/ja/validation/*`
- `docs/ja/operations/*`

---

## 2. Role Assignment / 役割分担

| Document | Role | 役割 |
|----------|------|------|
| `README.md` | EN project overview, quickstart, architecture | 英語プロジェクト概要 |
| `README_JP.md` | JA project overview, quickstart, architecture | 日本語プロジェクト概要 |
| `docs/INDEX.md` | Universal bilingual entry to docs/ | docs/ 全体のバイリンガル入口 |
| `docs/en/README.md` | EN documentation hub | 英語ドキュメントハブ |
| `docs/ja/README.md` | JA documentation hub | 日本語ドキュメントハブ |
| `docs/DOCUMENTATION_MAP.md` | Bilingual correspondence table | 英日対応表 |
| `docs/BILINGUAL_RULES.md` | This file: maintenance rules | 本ファイル: 運用ルール |

---

## 3. Rules for Adding New Documents / 新規文書追加ルール

### Decision Flow / 判断フロー

```
New document needed?
  ├── Is it user-facing (README, manual, getting-started)?
  │     └── YES → Type A: Create both EN and JA
  ├── Is it a technical spec, ADR, runbook, or benchmark?
  │     └── YES → Type B: Create in EN only under docs/en/
  ├── Is it a JA code review, audit, or JA community resource?
  │     └── YES → Type C: Create in JA only under docs/ja/
  └── Unsure?
        └── Default to Type B (EN only). Add JA later if needed.
```

### Placement Rules / 配置ルール

1. **EN documents** go under `docs/en/<category>/`
2. **JA documents** go under `docs/ja/<category>/`
3. **Language-neutral technical docs** (architecture, eu_ai_act, ui, benchmarks)
   remain at `docs/<category>/` as EN canonical
4. **Bilingual single-file docs** (INDEX.md, migration-guide) stay at `docs/` root
   or `docs/en/` with bilingual content
5. **Archive candidates** (dated reviews, snapshots) go to `docs/archive/`

### File Naming / ファイル命名規則

- Use **kebab-case**: `postgresql-production-guide.md`
- Permanent docs: **no date** in filename
- Dated reviews/snapshots: keep date as `*-YYYY-MM-DD.md` or `*_YYYY_MM_DD_ja.md`
- JA files in `docs/ja/`: no `_ja` suffix needed (directory implies language)
- New JA files in `docs/ja/`: use `_ja` suffix only if disambiguation is needed

---

## 4. Translation Status Labels / 翻訳状態ラベル

Use these labels in `DOCUMENTATION_MAP.md` and INDEX files:

| Label | Meaning | 意味 |
|-------|---------|------|
| `EN/JA` | Both languages available | 英日両方あり |
| `EN only` | English canonical, no JA version | 英語正本のみ |
| `JA only` | Japanese only, no EN version | 日本語のみ |
| `EN primary, JA summary` | EN is full, JA has summary/abstract | 英語完全版、日本語要約のみ |
| `JA primary, EN planned` | JA is full, EN translation planned | 日本語完全版、英語翻訳予定 |
| `Bilingual` | Single file with both EN and JA | 単一ファイルに英日両方 |

---

## 5. Handling Outdated Translations / 古い翻訳の扱い

1. If the EN canonical is updated but JA is not:
   - Add a note at the top of the JA version:
     `> **Note**: This translation may be outdated. See [EN version](path) for the latest.`
   - Update `DOCUMENTATION_MAP.md` status to `EN updated, JA outdated`

2. If JA is the canonical (Type C) and it's updated:
   - No EN action needed unless the document is promoted to Type A

3. Periodic review (quarterly recommended):
   - Check `DOCUMENTATION_MAP.md` for `outdated` entries
   - Prioritize Type A documents for re-translation

---

## 6. Archive Policy / アーカイブポリシー

- Dated review documents (`*_YYYY_MM_DD*.md`) are **immutable** once published
- When a new review supersedes an old one, move the old one to `docs/archive/`
- Archive files are never deleted, only moved
- `docs/archive/` has no bilingual requirement (preserve original language)

---

## 7. Cross-Reference Rules / 相互参照ルール

1. README.md links to EN docs paths (`docs/en/operations/...`)
2. README_JP.md links to JA docs paths when available, EN paths otherwise
3. Within `docs/en/`, link to other `docs/en/` files using relative paths
4. Within `docs/ja/`, link to other `docs/ja/` files using relative paths
5. Cross-language links: use `../en/...` or `../ja/...` relative paths
6. Always link to `docs/DOCUMENTATION_MAP.md` for the full correspondence table
