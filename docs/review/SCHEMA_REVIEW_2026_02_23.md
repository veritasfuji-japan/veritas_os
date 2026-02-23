# Schema 形状レビュー（2026-02-23）

対象: `veritas_os/api/schemas.py`  
観点: **API 契約の一貫性 / セキュリティ / 運用性 / フロントエンド実装容易性**

---

## 0. エグゼクティブサマリー

- 現状 schema は **後方互換性と可用性を最優先**した設計で、入力の揺らぎを高確率で吸収できる。
- 一方で、`extra="allow"` と強い coercion（自動変換）が広範に効いており、**仕様逸脱の早期検知**と**監査整合性**を弱めるリスクがある。
- フロントエンド視点では「通るが正しくない payload」が気づかれにくく、将来の strict 化時に破壊的影響が出やすい。
- 結論として、責務分離を維持したまま次の 3 段階を推奨する。
  1. **観測強化**（coercion の計測・可視化）
  2. **契約明文化**（OpenAPI + エラー仕様 + TS 型同期）
  3. **段階 strict 化**（warn → soft fail → forbid）

---

## 1. リクエスト schema（`DecideRequest`）の現状

### 1-1. 最小受理例

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

### 1-2. 実質的な受理挙動（互換吸収）

- `context`: dict 以外（`Context` オブジェクト、任意型）も受理し dict に正規化
- `alternatives` / `options`: list / dict / scalar / iterable を受理して list 化
- `options` のみ来た場合は `alternatives` へミラー
- `extra="allow"` により未知キーも保持

### 1-3. 主要フィールド

- `query: str`（最大 10,000 文字）
- `context: Dict[str, Any]`
- `alternatives: List[AltItem]`
- `options: List[AltItem]`（互換用途）
- `min_evidence: int`（0〜100）
- `memory_auto_put: bool`
- `persona_evolve: bool`

---

## 2. レスポンス schema（`DecideResponse`）の現状

### 2-1. 代表形

```json
{
  "request_id": "req_xxx",
  "chosen": {"id": "a", "title": "案A"},
  "alternatives": [
    {"id": "a", "title": "案A", "description": "説明", "score": 0.7}
  ],
  "evidence": [
    {
      "source": "web",
      "uri": "https://...",
      "title": "記事",
      "snippet": "...",
      "confidence": 0.8
    }
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

### 2-2. 実装上の特性

- `alternatives` / `options` は相互ミラー
- `evidence` は `dict | str | BaseModel | その他` を最終的に `EvidenceItem` に正規化
- `request_id` が未指定なら UUID 生成
- `trust_log` は dict から `TrustLog` への昇格を試行
- `extra="allow"` により未知キー維持

---

## 3. 現状評価（強み / リスク）

### 3-1. 強み

1. **高い受理性（可用性）**
   - 多様な入力揺らぎを落とさず吸収でき、API 利用障壁が低い。
2. **基本的な DoS 耐性**
   - 文字長・件数の上限を設ける設計がある。
3. **レスポンス回復力**
   - `evidence` / `alternatives` / `trust_log` などの変換で下流処理停止を回避しやすい。

### 3-2. リスク

1. **仕様逸脱の発見遅延**
   - `extra="allow"` と coercion により、本来エラーであるべき入力が通過しうる。
2. **クライアント品質劣化の潜在化**
   - FE/外部クライアントのバグがサーバ側で「救済」され、修正優先度が下がる。
3. **監査整合性の低下**
   - `trust_log` 変換失敗時の dict 温存で、監査データ構造の一貫性が崩れる可能性。
4. **契約の二重化**
   - `alternatives` と `options` の併存が、UI/SDK 実装で分岐コストを増やす。

---

## 4. フロントエンド観点の具体論点

### 4-1. 型安全性（TypeScript）

- 現状の「受理幅の広さ」は、TS 側で厳密型を敷いても実運用で乖離が発生しやすい。
- 特に `alternatives | options` の相互ミラーは、フォーム state と API DTO の境界でバグの温床になる。

### 4-2. UX / エラーハンドリング

- 不正入力が 4xx で返らないケースでは、ユーザーは誤入力に気づけない。
- 将来的に strict 化した際、同じ UI 操作が突然 4xx になる「遅延破壊」が起こりうる。

### 4-3. キャッシュ・再現性

- coercion 後の値がレスポンスやログに反映されると、
  FE が送った payload とサーバが採用した payload が一致しない場合がある。
- デバッグ時は「送信値」「正規化値」を分けて追える設計が望ましい。

### 4-4. 推奨（FE 含む契約運用）

- OpenAPI から TS 型を自動生成し、手書き型を禁止または最小化。
- UI の submit 前に Zod/Yup 等で **サーバ契約と同型の事前検証**を行う。
- `x-coerced-fields` のようなレスポンスメタ（またはログ項目）で、
  サーバが補正した項目を可視化する。

---

## 5. セキュリティ警告（重要）

- ⚠️ **重要**: アプリ層で長さ制限があっても、HTTP レイヤで body 上限が弱い場合、
  パース前に巨大 JSON を受理してメモリ圧迫するリスクが残る。
- ⚠️ **重要**: `extra="allow"` は意図しないメタデータ混入・ログ汚染・
  downstream 連携時の情報持ち出し面積拡大を招きうる。
- ⚠️ **重要**: coercion による「黙示的補正」は、入力改ざん検知や監査説明責任の観点で
  弱点になる可能性がある。

---

## 6. 改善提案（責務を越えない実装順）

> Planner / Kernel / Fuji / MemoryOS の責務分離を崩さず、`schemas.py` と API 境界で完結する提案に限定。

### Phase 1: 観測強化（破壊的変更なし）

1. coercion 発生時にイベント計測（例: `coercion.context_non_dict`, `coercion.evidence_string`）。
2. `trust_log` 昇格失敗を warning ログ + メトリクス化。
3. `extra` キー受理数を endpoint 単位でダッシュボード化。

### Phase 2: 契約明文化（クライアント同期）

1. OpenAPI に互換受理ルールを明記（入力例: 正常/救済/非推奨）。
2. FE/SDK へ配布する canonical DTO を `alternatives` へ一本化（`options` は deprecated 表示）。
3. エラー仕様を統一（`code`, `message`, `field`, `hint`）し、UI で再利用可能にする。

### Phase 3: 段階 strict 化（安全移行）

1. `extra="allow"` → `warn only`（ログ通知）
2. `warn only` → `soft fail`（ヘッダで警告、将来失敗告知）
3. 最終的に `extra="forbid"`（主要クライアント移行完了後）

---

## 7. 受け入れ基準（Done 条件）

- coercion メトリクスが可視化され、主要入力源の上位が特定できる。
- OpenAPI と FE 型の不一致件数がゼロ（CI チェック可）。
- `options` 利用率が閾値以下（例: 5% 未満）になってから strict 化に進む。
- body サイズ上限が Gateway/ASGI で明示設定され、運用手順書に記載済み。

---

## 8. 付録: クライアント向け推奨 payload（将来互換）

```json
{
  "query": "新機能AとBのどちらを先に実装すべきか",
  "context": {
    "user_id": "u123",
    "locale": "ja-JP",
    "timezone": "Asia/Tokyo"
  },
  "alternatives": [
    {
      "id": "feature_a",
      "title": "機能Aを先行",
      "description": "既存顧客の継続率改善を優先",
      "score": 0.0
    },
    {
      "id": "feature_b",
      "title": "機能Bを先行",
      "description": "新規獲得施策を優先",
      "score": 0.0
    }
  ],
  "min_evidence": 3,
  "memory_auto_put": true,
  "persona_evolve": false
}
```

`options` は互換のため受理されるが、新規実装では `alternatives` のみを利用する。

---

## 9. 実装反映メモ（2026-02-23 更新）

Phase 1（観測強化）として、`veritas_os/api/schemas.py` に以下を反映済み。

1. **coercion イベント可視化**
   - `DecideRequest` / `DecideResponse` に `coercion_events` を追加。
   - 代表イベント:
     - `coercion.context_non_mapping`
     - `coercion.options_to_alternatives`
     - `coercion.alternatives_to_options`
     - `coercion.request_extra_keys_allowed`
     - `coercion.response_extra_keys_allowed`
     - `coercion.trust_log_promotion_failed`

2. **`extra="allow"` 受理時の警告ログ**
   - request/response で未知キーを受け入れた際に warning を出力。
   - 互換性を維持しつつ、仕様逸脱の早期発見をしやすくした。

3. **レスポンス側の補正可視化**
   - `DecideResponse.meta["x_coerced_fields"]` に coercion イベントを格納。
   - FE/運用で「送信 payload と正規化結果の差分」を追跡可能。

4. **`trust_log` 昇格失敗の監査シグナル**
   - `dict -> TrustLog` 昇格に失敗した場合、raw を保持しつつ warning ログと
     `coercion.trust_log_promotion_failed` を付与。

### 未対応（継続課題）

- ⚠️ **セキュリティ継続課題**: `extra="allow"` は依然として受理面積を広げるため、
  Phase 3 の strict 化（warn → soft fail → forbid）が必要。
- ⚠️ **セキュリティ継続課題**: HTTP body サイズ上限は API schema 外の責務であり、
  Gateway/ASGI 側で明示設定が必要。
- ⚠️ **運用継続課題**: coercion イベントの集計ダッシュボード化（endpoint 別、クライアント別）は
  本書の提案どおり別途実装が必要。


## 10. 実装反映メモ（2026-02-24 追記）

Phase 2 準備（契約明文化に向けた互換運用）として、`alternatives` を正準フィールドに固定するための
追加観測を `veritas_os/api/schemas.py` に反映。

1. **deprecated フィールド使用の明示化（request）**
   - `options` が入力に含まれる場合、`deprecation.options_field_used` を付与。
   - warning ログで `alternatives` 利用を案内。

2. **競合入力の正準化（request）**
   - `alternatives` と `options` が同時指定かつ不一致の場合、
     `alternatives` を正として `options` を上書き。
   - `coercion.options_overridden_by_alternatives` を付与し、
     黙示補正を監査可能にした。

3. **競合出力の正準化（response）**
   - `alternatives` と `options` が不一致の場合、`options` を `alternatives` に同期。
   - `coercion.response_options_overridden_by_alternatives` を付与し、
     `meta["x_coerced_fields"]` から追跡可能。

4. **回帰防止テスト追加**
   - `veritas_os/tests/test_schemas_extra_v2.py` に request/response の競合ケースを追加。
   - 期待イベント付与と正準化結果（`options` が `alternatives` に一致）を検証。

### セキュリティ警告（継続）

- ⚠️ 本更新は **可観測性と契約一貫性の改善**であり、`extra="allow"` ポリシー自体は変更していない。
  したがって未知キー受理に伴うログ汚染・情報混入リスクは継続。
- ⚠️ HTTP body サイズ上限は引き続き Gateway/ASGI 側での明示設定が必要。

