# 巨大ファイルレビュー: 技術負債候補

**日付:** 2026-03-15
**対象:** 技術負債を防ぐために分割すべき1,000行超のソースファイル

---

## エグゼクティブサマリ

| 優先度 | ファイル | 行数 | 推奨分割数 |
|--------|------|------:|:----------:|
| 最重要 | `veritas_os/api/server.py` | 3,536 | 13モジュール |
| 最重要 | `veritas_os/core/memory.py` | 2,130 | 12モジュール |
| 高 | `veritas_os/core/eu_ai_act_compliance_module.py` | 2,036 | 6モジュール |
| 高 | `veritas_os/core/fuji.py` | 1,680 | 5モジュール |
| 高 | `veritas_os/core/planner.py` | 1,407 | 5モジュール |
| 高 | `frontend/app/audit/page.tsx` | 1,322 | 5コンポーネント |
| 高 | `veritas_os/tools/web_search.py` | 1,306 | 5モジュール |
| 中 | `veritas_os/core/pipeline.py` | 1,223 | 4モジュール |
| 中 | `veritas_os/core/world.py` | 1,084 | 未定 |
| 中 | `veritas_os/core/kernel.py` | 1,076 | 未定 |
| 中 | `veritas_os/api/schemas.py` | 1,039 | 未定 |

---

## 1. `veritas_os/api/server.py` (3,536行) — 最重要

### 現状

8クラス、76個のトップレベル関数、43個のAPIエンドポイント、6個のミドルウェアが1ファイルに集約されている。

### 特定された責務グループ

| グループ | 概算行数 | 説明 |
|---------|--------:|------|
| 認証・認可 | 700+ | APIキー検証、HMAC検証、AuthSecurityStore（Protocol + InMemory + Redis）、認証失敗追跡 |
| ミドルウェア・リクエスト処理 | 400+ | トレースID、レスポンスタイム、レート制限ヘッダ、ボディサイズ制限、セキュリティヘッダ、インフライト追跡 |
| トラストログ・監査 | 400+ | トラストログファイルI/O、検証、エクスポート、PROVドキュメント生成、統計 |
| コア意思決定API | 500+ | `/v1/decide`、`/v1/replay`、`/v1/fuji/validate`、エラーハンドリング、ペイロード変換 |
| ガバナンス・ポリシー | 350+ | ポリシーCRUD、価値ドリフト、アラート、RBAC/ABAC、四眼承認 |
| レート制限・ノンス管理 | 300+ | レートバケット追跡、ノンスリプレイ防止、スケジュールクリーンアップ |
| コンプライアンス・レポート | 250+ | EU AI Actレポート、デプロイ準備状況、コンプライアンス設定 |
| リアルタイムストリーミング | 200+ | SSEイベントハブ、`/v1/events`、WebSocket `/v1/ws/trustlog` |
| メモリストアAPI | 200+ | `/v1/memory/put`、`/v1/memory/search`、`/v1/memory/get`、`/v1/memory/erase` |
| システム制御 | 150+ | 緊急停止/再開、LLMプールクリーンアップ、グレースフルシャットダウン |
| 初期化・遅延ロード | 150+ | LazyState、起動時バリデーション、config/pipeline/FUJIの遅延インポート |
| ユーティリティ・ヘルパー | 250+ | エラーフォーマット、マスキング、ID生成、JSON操作 |

### 推奨分割構成

```
api/
├── server.py              # (~200行) FastAPIアプリ初期化、ライフスパン、ヘルスエンドポイント、ルート登録
├── auth.py                # (~700行) APIキー、HMAC、AuthSecurityStore、認証失敗追跡
├── rate_limiting.py       # (~300行) レートバケット、ノンスリプレイ防止、スケジュールクリーンアップ
├── middleware.py           # (~400行) トレースID、レスポンスタイム、セキュリティヘッダ、ボディサイズ制限
├── routes/
│   ├── decision.py        # (~500行) /v1/decide, /v1/replay, /v1/fuji/validate
│   ├── memory.py          # (~200行) /v1/memory/*
│   ├── trust.py           # (~400行) /v1/trust/*, /v1/trustlog/*
│   ├── governance.py      # (~350行) /v1/governance/*
│   ├── compliance.py      # (~250行) /v1/compliance/*, /v1/report/*
│   ├── system.py          # (~150行) /v1/system/*
│   └── streaming.py       # (~200行) /v1/events, /v1/ws/trustlog
├── config.py              # (~200行) CORS、遅延ロード、起動時バリデーション
└── utils.py               # (~250行) エラーフォーマット、マスキング、ID生成、JSON操作
```

### 分割しない場合のリスク

- **マージコンフリクト**: 43エンドポイントが1ファイルにあるため、並行開発が困難
- **テスト分離不可**: 認証ロジックを単体テストするのに全ルートのインポートが必要
- **認知負荷**: 3,500行超は人間の合理的な理解限界を超えている
- **デプロイ**: いずれかのエンドポイントの変更でもファイル全体のレビューが必要

---

## 2. `veritas_os/core/memory.py` (2,130行) — 最重要

### 現状

3クラス（`VectorMemory`、`MemoryStore`、`_LazyMemoryStore`）と30以上のモジュールレベル関数が、ベクトル検索・KVS永続化・ファイルロック・GDPRコンプライアンス・LLMベース蒸留・グローバル状態管理を混在させている。

### 特定された責務グループ

| グループ | 概算行数 | 説明 |
|---------|--------:|------|
| VectorMemory（埋め込み） | 415 | Sentence-transformer埋め込み、コサイン類似度、Base64 numpyによるJSON永続化 |
| MemoryStore（KVSコア） | 683 | JSONベースキーバリューストア、ファイルロック、インメモリTTLキャッシュ、ライフサイクルメタデータ |
| GDPR / コンプライアンス | 100+ | 監査証跡付きユーザー消去、セマンティック系統のカスケード削除、法的保持 |
| メモリ蒸留 | 200 | LLMによるエピソード記憶からセマンティック記憶への要約、プロンプトエンジニアリング |
| 検索オーケストレーション | 150 | デュアルモード検索（ベクトル → KVSフォールバック）、重複排除、ユーザーフィルタリング |
| エビデンスフォーマット | 80 | `/v1/decide`向けエビデンス変換 |
| モデルロード | 80 | ONNXモデルロード、外部モデル互換性 |
| グローバル状態 / 遅延初期化 | 100 | `_LazyMemoryStore`、グローバル`MEM`、`MEM_VEC`、ワンスオンリーガード |
| ファイルI/O・ロック | 70 | `locked_memory()`コンテキストマネージャ、POSIX fcntl / Windowsフォールバック |
| モジュールレベルAPIラッパー | 140 | `add()`、`put()`、`get()`、`search()`、`recent()`等 |

### 推奨分割構成

```
memory/
├── __init__.py            # (~100行) 公開APIエクスポート、モジュールレベルラッパー
├── vector.py              # (~250行) VectorMemoryクラス（埋め込み、検索）
├── store.py               # (~300行) MemoryStore KVSコア
├── lifecycle.py           # (~100行) 保持期間、有効期限、法的保持
├── compliance.py          # (~100行) ユーザー消去、カスケード削除、監査証跡
├── distillation.py        # (~150行) エピソード→セマンティックLLM要約
├── search.py              # (~150行) 検索オーケストレーション（ベクトル → KVSフォールバック）
├── evidence.py            # (~50行)  /v1/decide向けエビデンスフォーマット
├── storage.py             # (~150行) ファイルI/O、ロック、JSONシリアライゼーション
├── models.py              # (~80行)  モデルロード、外部互換性
└── config.py              # (~40行)  環境変数設定
```

### 分割しない場合のリスク

- **スレッド安全性**: 5つの独立したロックがファイル全体に散在し、並行性の推論が困難
- **コンプライアンス結合**: GDPRロジックがKVSに埋め込まれ、コンプライアンス監査が困難
- **2つのストレージバックエンド**（ベクトル + KVS）に明確な境界がない

---

## 3. `veritas_os/core/eu_ai_act_compliance_module.py` (2,036行) — 高

### 現状

5クラスと21個のトップレベル関数が、EU AI Act第5条、第9条、第10条、第12条、第13条、第14条、第15条、第50条のコンプライアンスを実装している。

### 特定された責務グループ

| グループ | 対応条項 | 概算行数 | 説明 |
|---------|---------|--------:|------|
| 禁止行為検出 | 第5条 | 360 | パターン正規化、n-gram類似度、多言語マッチング |
| リスク分類 | 第9条 | 30 | 附属書IIIハイリスクドメイン分類 |
| 人的監視 | 第14条 | 210 | `HumanReviewQueue`（SLA追跡、Webhook）、`SystemHaltController` |
| 文書化・透明性 | 第12条、第13条 | 300 | 改ざん防止トラストログ、第三者通知、ログ保持 |
| コンテンツ透かし | 第50条 | 80 | C2PA互換の透かしメタデータ |
| コンプライアンスパイプライン | 複数 | 140 | `/v1/decide`向け`eu_compliance_pipeline()`デコレータ |
| デプロイバリデーション | 第6条、第10条、第15条 | 500+ | PII安全性、合成データ、監査準備、法的承認、CEマーキング、データ品質 |
| 劣化モード | 第15条 | 50 | LLM利用不可時の安全な応答 |

### 推奨分割構成

```
compliance/
├── __init__.py                # 再エクスポート、後方互換性
├── prohibited_practices.py    # (~360行) 第5条: パターン検出、n-gram、正規化
├── human_oversight.py         # (~210行) 第14条: HumanReviewQueue、SystemHaltController
├── transparency.py            # (~300行) 第12/13条: トラストログ、通知、透かし
├── deployment_validation.py   # (~500行) 第6/10/15条: PII、データ品質、CEマーキング、法的承認
├── pipeline.py                # (~140行) コンプライアンスパイプラインデコレータ
└── config.py                  # (~50行)  EUComplianceConfig、保持期間設定
```

---

## 4. `veritas_os/core/fuji.py` (1,680行) — 高

### 現状

1データクラス（`SafetyHeadResult`）と30以上の関数が、FUJIセーフティゲート（ポリシーエンジン、LLM安全性評価、プロンプトインジェクション検出、多段階意思決定ロジック）を実装している。

### 特定された責務グループ

| グループ | 概算行数 | 説明 |
|---------|--------:|------|
| ポリシーエンジン | 430 | YAMLロード、ホットリロード、ランタイムパターンコンパイル、ポリシー適用 |
| セーフティヘッド評価 | 200 | LLMベース安全性スコアリング、フォールバックヒューリスティクス、ペナルティ適用 |
| プロンプトインジェクション検出 | 100 | インジェクション検出、テキスト正規化、スコアリング |
| コア意思決定ロジック | 350 | `fuji_core_decide()` — 多段階安全性評価、エビデンス確認、リスク集約 |
| 出力インターフェース | 300 | `fuji_gate()`、`validate_action()`、`posthoc_check()`、`evaluate()` |
| ユーティリティ・トラストログ | 200 | テキスト正規化、マスキング、FUJIコード選択、トラストイベント |

### 推奨分割構成

```
fuji/
├── __init__.py          # 再エクスポート
├── policy.py            # (~430行) ポリシーロード、ホットリロード、パターンコンパイル
├── safety_head.py       # (~200行) LLM安全性評価、フォールバックヒューリスティクス
├── injection.py         # (~100行) プロンプトインジェクション検出・スコアリング
├── core.py              # (~350行) fuji_core_decide()、リスク集約
└── gate.py              # (~300行) fuji_gate()、validate_action()、evaluate()
```

### 主要リスク

- `fuji_core_decide()`がセーフティヘッド + ポリシー + インジェクション + 決定論的ルールを深くネストされたロジックに集中 — コードベース中で最も高い単一関数複雑度

---

## 5. `veritas_os/core/planner.py` (1,407行) — 高

### 特定された責務グループ

| グループ | 概算行数 | 説明 |
|---------|--------:|------|
| JSON解析・抽出 | 680+ | 入力サニタイズ、安全なJSONレスキューとリトライ、複数戦略による抽出 |
| 計画判定ロジック | 190 | 単純Q&A検出、ステップ1検出、即時計画生成 |
| LLMプロンプトエンジニアリング | 130 | システム/ユーザープロンプト構築 |
| フォールバック・リカバリ | 80 | 超安全フォールバック計画、VERITASステージ推論 |
| ハイブリッド計画 | 180 | ワールドモデル + LLM統合、メモリスニペット取得 |
| コードタスク生成 | 140 | ベンチマークベースのコードタスク生成 |

### 推奨分割構成

```
planner/
├── __init__.py          # 再エクスポート、generate_plan()後方互換
├── json_parsing.py      # (~680行) JSON抽出、レスキュー、リトライ
├── detection.py         # (~190行) 単純QA検出、ステップ1検出
├── prompts.py           # (~130行) システム/ユーザープロンプト構築
├── fallback.py          # (~80行)  フォールバック計画、VERITASステージ推論
└── hybrid.py            # (~320行) ワールド+LLM計画、コードタスク生成
```

### 注目すべき懸念点

- JSON解析がファイルの約48%を占有 — 明確な抽出候補

---

## 6. `frontend/app/audit/page.tsx` (1,322行) — 高

### 現状

単一のReactコンポーネント（`TrustLogExplorerPage`）に、全state、hooks、ハンドラ、JSXが集約されている。

### 推奨分割構成

```
frontend/app/audit/
├── page.tsx                  # (~100行) メインページ、サブコンポーネントのコンポジション
├── constants.ts              # (~60行)  ステータス色、ページ上限
├── hooks/
│   └── useAuditData.ts       # (~200行) データ取得、フィルタリング、ソート、メモ化
├── handlers/
│   └── useAuditActions.ts    # (~250行) 検証、エクスポート、レポート、検索ハンドラ
└── components/
    ├── SearchPanel.tsx        # (~150行) リクエストID検索、横断検索
    ├── TimelineList.tsx       # (~250行) トラストログエクスプローラーリスト
    ├── DetailPanel.tsx        # (~200行) サマリ、メタデータ、ハッシュタブ
    └── ExportPanel.tsx        # (~150行) 日付範囲、フォーマット選択、ダウンロード
```

---

## 7. `veritas_os/tools/web_search.py` (1,306行) — 高

### 特定された責務グループ

| グループ | 概算行数 | 説明 |
|---------|--------:|------|
| SSRF・DNSリバインディング防御 | 160 | ホスト名正規化、プライベートホスト検出、DNS解決、リバインディングガード |
| 設定・認証情報 | 100 | 環境変数、APIキー解決、許可リスト解析 |
| クエリ強化・フィルタリング | 100 | AGI検出、VERITASアンカー、クエリブースト、結果ブロック |
| 有害コンテンツ・安全性 | 60 | 有害結果検出、Base64ペイロード検査 |
| HTTP・リトライロジック | 80 | 指数バックオフ、リトライステータス判定 |
| メインオーケストレータ | 400+ | `web_search()`エントリポイント、結果正規化 |
| 安全なパラメータ解析 | 90 | `_safe_int()`、`_safe_float()`、範囲バリデーション |

### 推奨分割構成

```
tools/
├── web_search.py              # (~400行) メインオーケストレータ、結果正規化
├── web_search_security.py     # (~160行) SSRF/DNSリバインディング防御
├── web_search_config.py       # (~100行) 認証情報、許可リスト、安全な解析
├── web_search_filtering.py    # (~100行) AGI検出、クエリブースト、ブロック
└── web_search_safety.py       # (~60行)  有害コンテンツ検出、Base64検査
```

---

## 8. `veritas_os/core/pipeline.py` (1,223行) — 中

### 特定された責務グループ

| グループ | 概算行数 | 説明 |
|---------|--------:|------|
| 初期化・インポート | 100 | モジュールチェック、ペルソナロード、警告設定 |
| ユーティリティ・ヘルパー | 120 | 型変換、値クリッピング、リクエストパラメータ抽出 |
| 永続化・ストレージ | 180 | パス解決、意思決定ロード、データセット/トラストログフォールバック |
| ポリシー・ゲートロジック | 100 | ゲート予測、バリュー統計、代替案重複排除 |
| メインオーケストレーション | 200+ | `run_decide_pipeline()` — ステージモジュールへの委譲 |

### 推奨分割構成

```
pipeline/
├── __init__.py           # 再エクスポート
├── pipeline.py           # (~200行) メインrun_decide_pipeline()オーケストレータ
├── persistence.py        # (~180行) パス解決、意思決定ロード、フォールバック
├── helpers.py            # (~120行) 型変換、クリッピング、パラメータ
└── gate.py               # (~100行) ゲート予測、バリュー統計、重複排除
```

---

## 要注意テストファイル

複数のテストファイルも適正なサイズを超えており、整理が必要:

| ファイル | 行数 | 備考 |
|---------|-----:|------|
| `tests/test_api_server_extra.py` | 1,886 | server.pyの分割に合わせるべき |
| `tests/test_coverage_boost.py` | 1,380 | 機能別に分割を検討 |
| `tests/test_kernel_core_extra.py` | 1,217 | カーネルの責務別に分割 |
| `tests/test_api_pipeline.py` | 1,128 | パイプラインステージ別に分割 |
| `packages/types/src/index.test.ts` | 1,590 | 型ドメイン別に分割 |

---

## 推奨実行順序

1. **`api/server.py`** — 最大行数、最も多様な責務、並行開発のボトルネック
2. **`core/memory.py`** — 散在する並行性の懸念を持つ重要インフラ
3. **`core/fuji.py`** — 安全性に関わるコードは分離テストの恩恵が最大
4. **`core/eu_ai_act_compliance_module.py`** — 規制関連コードは明確に分離すべき
5. **`frontend/app/audit/page.tsx`** — 標準的なReactコンポーネント分割
6. ~~**`tools/web_search.py`** — セキュリティ上重要なSSRFロジックを分離すべき~~ **完了**
7. ~~**`core/planner.py`** — JSON解析が支配的; 直接的な抽出が可能~~ **完了**
8. **`core/pipeline.py`** — 既にサブモジュールへの部分的委譲あり

---

## 実施済み改善 (2026-03-15)

### 7. `core/planner.py` — JSON解析モジュール分離

**変更内容:** JSON解析・救出ロジック（~274行）を `core/planner_json.py` に抽出

| 項目 | 変更前 | 変更後 |
|------|-------:|-------:|
| `planner.py` | 1,407行 | 1,133行 |
| `planner_json.py` | — | 304行 |

**抽出した関数:**
- `_truncate_json_extract_input()` — BOM/NUL除去、サイズ制限
- `_safe_parse()` — dict/list/str 統一パーサ（fenced JSON対応）
- `_safe_json_extract_core()` — LLM出力からのJSON救出エンジン（4段階フォールバック）
- `_safe_json_extract()` — 後方互換ラッパー
- 関連定数: `_MAX_JSON_EXTRACT_CHARS`, `_MAX_JSON_DECODE_ATTEMPTS` 等

**後方互換性:** `planner.py` が `planner_json` から全シンボルを再インポートするため、既存のインポートパスは変更不要。

---

### 6. `tools/web_search.py` — SSRFセキュリティモジュール分離

**変更内容:** SSRF/DNS rebinding防御ロジック（~214行）を `tools/web_search_security.py` に抽出

| 項目 | 変更前 | 変更後 |
|------|-------:|-------:|
| `web_search.py` | 1,306行 | 1,120行 |
| `web_search_security.py` | — | 294行 |

**抽出した関数:**
- `_sanitize_websearch_url()` — HTTPS強制、埋め込み資格情報禁止
- `_extract_hostname()` / `_canonicalize_hostname()` — ホスト名正規化
- `_is_obviously_private_or_local_host()` — 文字列ベースのプライベートホスト検出
- `_resolve_host_infos()` — LRUキャッシュ付きDNS解決
- `_is_private_or_local_host()` — DNS解決ベースのSSRF検出
- `_resolve_public_ips_uncached()` — リクエスト時DNS解決（rebindingガード用）
- `_extract_public_ips_for_url()` / `_validate_rebinding_guard()` — DNS rebinding防御
- `_is_hostname_exact_or_subdomain()` — サブドメイン判定

**後方互換性:** テストが `web_search_mod` 経由で monkeypatch するパターンに対応するため、`_is_allowed_websearch_url()` と `_validate_rebinding_guard()` は `web_search.py` にローカルラッパーとして維持。全107テスト（test_web_search.py: 45, test_web_search_extra.py: 62）パス。

---

### 改善効果サマリ

| メトリクス | 変更前 | 変更後 | 削減率 |
|-----------|-------:|-------:|-------:|
| `planner.py` 行数 | 1,407 | 1,133 | -19.5% |
| `web_search.py` 行数 | 1,306 | 1,120 | -14.2% |
| セキュリティコード分離 | 未分離 | 独立モジュール | — |
| JSON解析分離 | 未分離 | 独立モジュール | — |
