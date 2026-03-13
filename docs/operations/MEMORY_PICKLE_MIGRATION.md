---
title: MemoryOS Legacy Pickle Migration
lifecycle: active
updated_at: 2026-03-13
---

# MemoryOS Legacy Pickle Migration

## Security policy

- Runtime での `pickle` / `joblib` / `.pickle` 読み込みは **永久に禁止** です。
- 理由: `pickle` は任意コード実行 (RCE) リスクを持つためです。
- Runtime が `.pkl` / `.joblib` / `.pickle` を検知した場合、ロードせずに `[SECURITY]` エラーログを出力します。
- **自動移行は行いません** — 変換は明示的な CLI 操作のみで実行されます。

## 旧形式の廃止

- pickle / joblib のランタイム読み込みは **完全に廃止** されました（期限なし）。
- `VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION` 環境変数は無効です。設定しても効果はありません。
- `joblib_load` シンボルはメモリモジュールから削除されました。
- `enable_memory_joblib_model` のデフォルトは `False` に変更されました。

## Migration CLI

旧 pickle 資産がある場合は、以下のコマンドで安全な JSON 形式に変換してください。

### 基本コマンド

```bash
# デフォルトディレクトリ（core/models）をスキャン＆変換
python -m veritas_os.scripts.migrate_pickle

# 特定のディレクトリを指定
python -m veritas_os.scripts.migrate_pickle --scan-dir /path/to/legacy/data

# ドライラン（変換せず対象ファイルのみ表示）
python -m veritas_os.scripts.migrate_pickle --dry-run

# 詳細ログ
python -m veritas_os.scripts.migrate_pickle --verbose
```

### 変換フロー

1. CLI がスキャンディレクトリ内の `.pkl` / `.joblib` / `.pickle` ファイルを検出
2. `RestrictedUnpickler` で安全なクラスのみを許可してデシリアライズ
3. JSON 形式 (`*.json`) に変換して同ディレクトリに出力
4. **元の pickle ファイルは自動削除されません** — 手動で削除してください

### セキュリティ上の注意

- 信頼できる隔離環境でのみ実行してください
- 最大ファイルサイズ: 50 MiB
- 許可クラスリスト外のオブジェクトを含む pickle は変換に失敗します
- 不明な出自の `.pkl` ファイルに対しては **絶対に実行しないでください**

## 変換先フォーマット

| 旧形式 | 新形式 | 説明 |
|--------|--------|------|
| `vector_index.pkl` | `vector_index.json` | VectorMemory インデックス（embeddings は Base64 エンコード） |
| `memory_model.pkl` | `memory_model.onnx` + `memory_model.metadata.json` | モデルは `memory_train.py` で ONNX にエクスポート |
| その他 `.pkl` | `*.json` | 汎用変換（JSON シリアライズ可能な構造のみ） |

## 運用手順

### 移行作業

1. **バックアップ**: 旧 pickle ファイルを安全な場所にコピー
2. **隔離環境で変換**: `python -m veritas_os.scripts.migrate_pickle --scan-dir <path>`
3. **検証**: 変換後の JSON ファイルが正しいことを確認
4. **配置**: JSON ファイルを本番ディレクトリに配置
5. **削除**: 旧 pickle ファイルを本番ディレクトリから削除
6. **CI 確認**: `python scripts/security/check_runtime_pickle_artifacts.py` が通ることを確認

### CI ガードレール

- `scripts/security/check_runtime_pickle_artifacts.py` — ランタイムディレクトリに `.pkl` / `.joblib` / `.pickle` が存在しないことを検証
- デプロイ前に必ず実行してください

## Operational warning

- 本番ディレクトリに未検証 `.pkl` / `.joblib` / `.pickle` を置かないでください
- CI/CD パイプラインでの `.pkl` ファイル混入検知を有効にしてください
- 新規コードで `pickle.load()` / `joblib.load()` を使用しないでください
