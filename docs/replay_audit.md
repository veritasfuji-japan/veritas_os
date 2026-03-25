# Replay Engine — 監査機能ドキュメント

## 概要

Replay エンジンは、過去の意思決定を確定的に再実行し、元の出力と比較する
**監査中核機能**です。replay レポートは JSON アーティファクトとして
`audit/replay_reports/` に保存され、監査証跡として利用できます。

## エンドポイント

| Method | Path | 認証 | 用途 |
|--------|------|------|------|
| POST | `/v1/replay/{decision_id}` | HMAC + API Key | 主要 replay API |
| POST | `/v1/decision/replay/{decision_id}` | API Key | レガシー replay API |

## Replay Artifact Schema

すべての replay レポートには `schema_version` フィールドが含まれます。
バージョンが変更された場合、下流の監査ツールは互換性を検出できます。

**現行バージョン:** `1.0.0`

### レポート構造

```json
{
  "schema_version": "1.0.0",
  "decision_id": "dec-123",
  "replay_time_ms": 2500,
  "strict": true,
  "match": false,
  "severity": "critical",
  "divergence_level": "critical_divergence",
  "audit_summary": "Replay dec-123 (strict): MISMATCH (critical) — Decision output differs.",
  "diff": {
    "high_level": ["Decision output differs."],
    "fields_changed": ["decision"],
    "field_details": [
      {
        "field": "decision",
        "severity": "critical",
        "before": {"output": "allow"},
        "after": {"output": "reject"}
      }
    ],
    "max_severity": "critical",
    "divergence_level": "critical_divergence",
    "before": { "..." : "..." },
    "after": { "..." : "..." }
  },
  "meta": {
    "created_at": "2026-03-25T11:00:00Z",
    "pipeline_version": "abc1234",
    "notes": "...",
    "external_dependency_versions": {
      "python_version": "3.12.0",
      "platform": "linux-x86_64",
      "packages": {"openai": "1.0.0"}
    }
  }
}
```

## Diff Severity 分類

各フィールドの変更には、監査上の重大度が付与されます。

| Severity | フィールド | 意味 |
|----------|-----------|------|
| `critical` | `decision`, `fuji` | 判断結果またはコンプライアンス判定が変化。即座に調査が必要 |
| `warning` | `value_scores` | 価値評価スコアが変化。判断への影響を確認すべき |
| `info` | `evidence`, その他 | 証拠セットや付加情報の差異。通常は許容範囲 |

## Divergence Level（乖離レベル）

全体的な乖離の深刻度を一言で分類します。

| Level | 条件 | 監査アクション |
|-------|------|----------------|
| `no_divergence` | 差分なし（match=true） | 対応不要 |
| `acceptable_divergence` | warning/info のみの差分 | 記録のみ。定期レビュー時に確認 |
| `critical_divergence` | critical な差分あり | 即座に調査・是正措置が必要 |

## Audit Summary

`audit_summary` フィールドは、監査担当者が一目で結果を把握できる
人間可読な要約です。

例:
- `Replay dec-123 (strict): MATCH — no divergence detected.`
- `Replay dec-456 (standard): MISMATCH (critical) — Decision output differs. Fuji result differs.`

## Strict Mode

環境変数 `VERITAS_REPLAY_STRICT=1` または API パラメータで有効化。

Strict モードでは:
- `temperature=0` に固定
- 外部 API をモック化（`_mock_external_apis=True`）
- メモリストアを無効化
- 元のシードを使用

## 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `VERITAS_REPLAY_STRICT` | Strict モードの有効化 | `false` |
| `VERITAS_PIPELINE_VERSION` | Git SHA のオーバーライド | 自動検出 |
| `VERITAS_REPLAY_ENFORCE_MODEL_VERSION` | モデルバージョン検証 | `1` (有効) |
| `VERITAS_REPLAY_REQUIRE_MODEL_VERSION` | スナップショットにモデルバージョン必須 | `1` (有効) |
| `VERITAS_MODEL_NAME` / `LLM_MODEL` | 現在のモデル名（検証用） | — |

## API レスポンス

### POST /v1/replay/{decision_id}

```json
{
  "ok": true,
  "decision_id": "dec-123",
  "replay_path": "/path/to/report.json",
  "match": false,
  "diff_summary": "fields_changed=decision,fuji",
  "replay_time_ms": 2500,
  "schema_version": "1.0.0",
  "severity": "critical",
  "divergence_level": "critical_divergence",
  "audit_summary": "Replay dec-123 (standard): MISMATCH (critical) — Decision output differs. Fuji result differs."
}
```

## フロントエンド

`ReplayDiffViewer` コンポーネントは、フィールドごとの severity に基づいて
視覚的な差分表示を行います。

- **Critical** フィールド: 赤系の背景 + 左ボーダー + `CRITICAL` ラベル
- **Warning** フィールド: 黄系の背景 + 左ボーダー + `WARNING` ラベル
- **Info** フィールド: 通常表示
- ヘッダーには divergence level のバッジが表示されます
