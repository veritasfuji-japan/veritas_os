---
title: MemoryOS Legacy Pickle Migration
lifecycle: active
updated_at: 2026-03-12
---

# MemoryOS Legacy Pickle Migration

## Security policy

- Runtime での `pickle` / `joblib` 読み込みは **禁止** です。
- 理由: `pickle` は任意コード実行 (RCE) リスクを持つためです。
- Runtime が `.pkl` を検知した場合、ロードせずに `[SECURITY]` ログを出力します。

## Sunset deadline

- Pickle runtime block policy deadline: **2026-06-30**
- この日付以降、runtime 側での例外的な互換復帰は行いません。

## Offline migration steps

1. 信頼できる隔離環境で旧 `.pkl` を読み込みます。
2. `VectorMemory` の JSON 形式 (`vector_index.json`) に変換します。
3. モデルは ONNX (`memory_model.onnx`) へ変換します。
4. 本番配置前に `.pkl` を削除し、JSON/ONNX のみを配置します。

## Operational warning

- 本番ディレクトリに未検証 `.pkl` を置かないでください。
- CI/CD で `.pkl` ファイル混入を検知するチェックを推奨します。
