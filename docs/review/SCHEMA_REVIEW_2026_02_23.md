# Schema 形状レビュー（2026-02-23）

対象: `veritas_os/api/schemas.py`

## 1. リクエスト schema（`DecideRequest`）の形

最小形:

```json
{
  "query": "意思決定したい内容",
  "context": {
    "user_id": "u123",
    "query": "意思決定したい内容"
  },
  "alternatives": [
    {"id": "a", "title": "案A", "description": "説明", "score": 0.7}
  ]
}
```

実際には以下を許容:

- `context`: dict 以外（`Context` オブジェクト、任意型）も受理し dict に正規化
- `alternatives` / `options`: list / dict / scalar / iterable を受理して list 化
- `options` のみ来た場合は `alternatives` へミラー
- `extra="allow"` により未知キーも保持

主要フィールド:

- `query: str`（最大 10,000 文字）
- `context: Dict[str, Any]`
- `alternatives: List[AltItem]`
- `options: List[AltItem]`（互換用途）
- `min_evidence: int`（0〜100）
- `memory_auto_put: bool`
- `persona_evolve: bool`

---

## 2. レスポンス schema（`DecideResponse`）の形

代表形:

```json
{
  "request_id": "req_xxx",
  "chosen": {"id": "a", "title": "案A"},
  "alternatives": [
    {"id": "a", "title": "案A", "description": "説明", "score": 0.7}
  ],
  "evidence": [
    {"source": "web", "uri": "https://...", "title": "記事", "snippet": "...", "confidence": 0.8}
  ],
  "critique": [],
  "debate": [],
  "decision_status": "allow",
  "gate": {"risk": 0.1, "telos_score": 0.8, "decision_status": "allow"},
  "trust_log": {
    "request_id": "req_xxx",
    "created_at": "2026-02-23T00:00:00Z",
    "sources": [],
    "critics": [],
    "checks": [],
    "approver": "system"
  }
}
```

実装上の特性:

- `alternatives` / `options` は相互ミラー
- `evidence` は `dict | str | BaseModel | その他` を最終的に `EvidenceItem` に正規化
- `request_id` が未指定なら UUID 生成
- `trust_log` は dict から `TrustLog` への昇格を試行
- `extra="allow"` により未知キー維持

---

## 3. レビュー所見（要点）

### 良い点

1. **後方互換性が高い**
   - 多様な入力型を受理し、落とさず正規化できる。
2. **DoS 耐性の基本対策がある**
   - 文字長やリスト件数の上限が定義されている。
3. **レスポンス頑健性が高い**
   - `evidence` / `alternatives` / `trust_log` などで型ゆらぎを吸収する。

### 懸念点

1. **`extra="allow"` が広範囲**
   - 想定外キーが静かに通るため、仕様逸脱やデータ汚染の検知が遅れる。
2. **過度な自動補完によるサイレント変換**
   - `str` や不正型を受けても通るため、クライアント不具合が埋もれやすい。
3. **`trust_log` の失敗時フォールバック**
   - `TrustLog` 化に失敗すると dict を温存するため、監査データの一貫性が崩れうる。

### セキュリティ警告

- ⚠️ **重要**: 長さ制限はあるが、HTTP レイヤでのボディサイズ制限が弱いと、
  パース前に巨大 JSON を受け付けるリスクが残る。
- ⚠️ **重要**: `extra="allow"` の常用は、意図しないメタデータ混入やログ汚染の温床になり得る。

---

## 4. 改善提案（責務を越えない範囲）

1. `DecideRequest` について、運用段階で `extra="forbid"` への段階移行計画を用意する。
2. `evidence` / `trust_log` の「救済変換」をメトリクス化し、頻度が高い入力源を修正対象にする。
3. API Gateway / ASGI ミドルウェアで `max request body size` を明示設定する。
4. OpenAPI 側に「互換受理（coercion）」の挙動を明文化し、クライアント実装差を減らす。

