# VERITAS OS — File-to-PostgreSQL Migration Guide

## 概要 / Overview

`veritas-migrate` CLI は、ファイルベースのバックエンド（JSON Memory と JSONL TrustLog）
から PostgreSQL バックエンドへデータを安全に移行します。

The `veritas-migrate` CLI safely migrates data from file-based backends
(JSON Memory and JSONL TrustLog) to the PostgreSQL backend.

---

## 移行設計原則 / Migration Design Principles

| 原則 / Principle | 実装 / Implementation |
|---|---|
| **Idempotent** | 既存の `(key, user_id)` / `request_id` は再書き込みしない |
| **Chain-preserving** | TrustLog の `sha256` / `sha256_prev` を verbatim 保存 |
| **Fail-soft** | 1エントリの失敗で中断せず、レポートに記録して継続 |
| **Dry-run** | `--dry-run` で移行対象件数を事前確認できる |
| **Observable** | 毎回構造化レポートを出力（JSON 出力も可） |

---

## 前提条件 / Prerequisites

1. **PostgreSQL が稼働中** で Alembic マイグレーション済み:

   ```bash
   alembic upgrade head
   ```

2. **環境変数** が設定済み:

   ```bash
   export VERITAS_DATABASE_URL="postgresql://user:pass@localhost:5432/veritas"
   export VERITAS_ENCRYPTION_KEY="<base64-32-byte-key>"   # TrustLog 復号に必要
   ```

3. **推奨**: 移行中は TrustLog への新規書き込みを停止するか、サービスを止める。
   Memory 移行は並列実行でも安全。

---

## インストール / Installation

```bash
pip install ".[postgresql]"
# または
pip install ".[full]"
```

---

## コマンドリファレンス / Command Reference

### `veritas-migrate memory`

JSON Memory ファイル → PostgreSQL `memory_records` テーブル

```
veritas-migrate memory --source <PATH> [--dry-run] [--batch-size N] [--json] [-v]
```

| オプション | 説明 |
|---|---|
| `--source PATH` | ソース `memory.json` ファイルパス（必須） |
| `--dry-run` | 書き込みなし — 移行件数のみ確認 |
| `--batch-size N` | バッチサイズ（デフォルト: 500、将来の最適化用） |
| `--json` | レポートを JSON で出力 |
| `-v / --verbose` | 詳細ログを有効化 |

### `veritas-migrate trustlog`

JSONL TrustLog ファイル → PostgreSQL `trustlog_entries` テーブル

```
veritas-migrate trustlog --source <PATH> [--dry-run] [--verify] [--batch-size N] [--json] [-v]
```

| オプション | 説明 |
|---|---|
| `--source PATH` | ソース `trust_log.jsonl` ファイルパス（必須） |
| `--dry-run` | 書き込みなし — 移行件数のみ確認 |
| `--verify` | 移行後に PostgreSQL のハッシュチェーン整合性を検証 |
| `--batch-size N` | バッチサイズ（デフォルト: 500） |
| `--json` | レポートを JSON で出力 |
| `-v / --verbose` | 詳細ログを有効化 |

---

## 使い方 / Usage Examples

### Step 1 — Dry-run (事前確認)

```bash
# Memory 移行のプレビュー
veritas-migrate memory \
  --source /data/logs/memory.json \
  --dry-run

# TrustLog 移行のプレビュー
veritas-migrate trustlog \
  --source /data/logs/trust_log.jsonl \
  --dry-run
```

サンプル出力:

```
============================================================
VERITAS OS Migration Report
============================================================
  Source:     /data/logs/memory.json
  Dry-run:    True

  Migrated:   1523
  Duplicates: 0
  Skipped:    0
  Malformed:  0
  Failed:     0
  Total:      1523
============================================================
Status: PASS
============================================================
```

### Step 2 — 本番移行

```bash
# Memory を移行
veritas-migrate memory \
  --source /data/logs/memory.json

# TrustLog を移行（移行後にチェーン整合性を検証）
veritas-migrate trustlog \
  --source /data/logs/trust_log.jsonl \
  --verify
```

### Step 3 — JSON 出力 (CI/スクリプト統合)

```bash
veritas-migrate trustlog \
  --source /data/logs/trust_log.jsonl \
  --verify \
  --json | jq '.verify_ok'
```

### Step 4 — 再実行安全性の確認

```bash
# 再実行してもエラーにならない（全件 duplicate）
veritas-migrate memory \
  --source /data/logs/memory.json
# → Duplicates: 1523, Migrated: 0, Status: PASS
```

---

## 移行レポートの見方 / Understanding the Report

```json
{
  "source": "/data/logs/trust_log.jsonl",
  "migrated":   1000,    // PostgreSQL に新規書き込みした件数
  "duplicates":  200,    // 既存エントリをスキップした件数（再実行分）
  "skipped":       0,    // 期限切れなど意図的にスキップした件数
  "malformed":     2,    // パース失敗 / 必須フィールド欠如
  "failed":        0,    // DB エラーで書き込み失敗した件数
  "dry_run":    false,
  "verify_ok":  true,    // --verify の結果（null = 未実行）
  "verify_detail": { ... },
  "errors": [...]        // 個別エラーの詳細（最大 200 件）
}
```

**exit code**:

| コード | 意味 |
|---|---|
| `0` | 成功（failed=0 かつ malformed=0） |
| `1` | 部分失敗（failed>0 または malformed>0） |
| `2` | 致命的エラー（引数不正、DB 接続不能など） |

---

## TrustLog 移行の暗号セマンティクス / Cryptographic Semantics

`veritas-migrate trustlog` は以下を保証します:

1. **ハッシュチェーン保存**: `sha256` / `sha256_prev` フィールドを verbatim で
   PostgreSQL に格納。`prepare_entry()` は **呼ばない**。

2. **redact 済みデータをそのまま保存**: JSONL に保存された時点で既に
   PII redaction 済みのエントリを保存。再 redact は行わない。

3. **チェーン状態更新**: 各インポート成功後に `trustlog_chain_state.last_hash` /
   `last_id` を更新（条件付き: 新しい `id` が既存 `last_id` より大きい場合のみ）。

4. **暗号化ファイルのサポート**: `ENC:` プレフィックス付きの暗号化行は
   `VERITAS_ENCRYPTION_KEY` で自動復号してから PostgreSQL に JSONB として格納。

> **Note**: PostgreSQL バックエンドは TrustLog を平文 JSONB で保存します
> （PostgreSQL の transport/connection 層で暗号化を担保します）。
> これはファイルバックエンドの「at-rest encryption」とは設計上異なります。

---

## 移行後の検証 / Post-Migration Verification

### `--verify` によるチェーン整合性確認

```bash
veritas-migrate trustlog \
  --source /data/logs/trust_log.jsonl \
  --verify
```

`--verify` は PostgreSQL の `trustlog_entries` テーブルを全件スキャンし、
`sha256_prev` チェーンが連続しているかを確認します。

### 既存の TrustLog verifier との組み合わせ

```bash
# ソース JSONL のチェーンを検証（移行前の健全性確認）
veritas-trustlog-verify --full-ledger /data/logs/trust_log.jsonl

# 移行後に PostgreSQL チェーンを検証
veritas-migrate trustlog \
  --source /data/logs/trust_log.jsonl \
  --dry-run --verify --json | jq '.verify_ok'
```

---

## ローテーション済みファイルの移行 / Migrating Rotated Log Files

複数のローテーション済みファイルを移行する場合:

```bash
# 古い順に移行（チェーンの連続性を保つ）
for f in trust_log_old.jsonl trust_log.jsonl; do
  veritas-migrate trustlog --source /data/logs/$f
done
```

再実行は安全です。`request_id` で重複チェックされるため、
同じエントリが二重に書き込まれることはありません。

---

## トラブルシューティング / Troubleshooting

### `EncryptionKeyMissing` エラー

```
VERITAS_ENCRYPTION_KEY is not set
```

解決: `VERITAS_ENCRYPTION_KEY` 環境変数を設定してください。

### `PostgreSQL connection pool unavailable`

```
RuntimeError: PostgreSQL connection pool unavailable: ...
```

解決: `VERITAS_DATABASE_URL` を確認し、PostgreSQL が稼働中であることを確認してください。

### `malformed: N` が多い

- 暗号鍵が正しいか確認
- ソースファイルが破損していないか確認（`verify_full_ledger` で検証可能）
- `--verbose` でエラー詳細を確認

---

## 制約事項 / Limitations

1. **Memory: expired records の移行はスキップ** — `list_all()` は期限切れレコードを
   返さない。期限切れのレコードも移行したい場合は個別対応が必要。

2. **TrustLog: ローテーション済みファイルは別途実行** — アクティブな
   `trust_log.jsonl` のみ自動検出しない。全ファイルを明示的に指定する必要あり。

3. **並列実行非推奨** — TrustLog 移行中にアクティブなサービスが TrustLog に
   書き込むと、チェーン state の更新順序が乱れる可能性がある。

4. **PostgreSQL chain verify は file-based verifier と別実装** — `--verify` は
   `sha256_prev` の連続性のみ確認。署名検証・TSA検証には
   `veritas-trustlog-verify` を使用。

5. **バッチサイズパラメータは現在未使用** — 将来の大規模移行最適化用に予約済み。

---

## 変更ファイル一覧 / Changed Files

| ファイル | 変更内容 |
|---|---|
| `veritas_os/cli/migrate.py` | 新規追加 — 移行 CLI 本体 |
| `veritas_os/storage/postgresql.py` | `PostgresTrustLogStore.import_entry()` / `PostgresMemoryStore.import_record()` 追加 |
| `veritas_os/tests/test_cli_migrate.py` | 新規追加 — 8シナリオのテスト |
| `pyproject.toml` | `veritas-migrate` エントリポイント追加 |
| `docs/migration-guide.md` | このファイル |

---

## 後方互換性 / Backward Compatibility

- 既存の JSON / JSONL バックエンドは変更なし
- `PostgresTrustLogStore.append()` の挙動は変更なし
- `PostgresMemoryStore.put()` の挙動は変更なし
- 追加したメソッド (`import_entry`, `import_record`) はオプショナル — 既存コードへの影響なし
