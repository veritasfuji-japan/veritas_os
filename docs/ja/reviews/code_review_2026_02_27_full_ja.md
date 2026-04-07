# VERITAS OS 全コードレビューレポート

**日付:** 2026-02-27
**対象:** 全ソースコード（約128,000行、411ファイル）
**レビュー範囲:** core/, api/, memory/, logging/, tools/, scripts/, frontend/, packages/, インフラ、テスト

---

## エグゼクティブサマリー

VERITAS OSは全体として**堅牢なセキュリティ意識と高い設計品質**を示しています。スレッドセーフティ、暗号学的監査ログ、入力バリデーションが一貫して実装されています。ただし、以下の改善が必要です：

| 深刻度 | 件数 | 主な分類 |
|--------|------|----------|
| **CRITICAL** | 5 | メモリユーザー分離、CSPヘッダー、エラーバウンダリ欠如 |
| **HIGH** | 12 | レート制限、ゼロ除算、パス走査、レース条件 |
| **MEDIUM** | 18 | バリデーション不足、ハードコード値、型安全性 |
| **LOW** | 15 | ドキュメント、ログ品質、軽微なコード品質 |

---

## 1. CRITICAL（即時対応必須）

### C-1. メモリAPI ユーザー分離不備
- **場所:** `veritas_os/api/server.py:1577, 1684-1686`
- **問題:** `/v1/memory/put` は `user_id = body.get("user_id", "anon")` でデフォルト "anon" を許容。任意のAPIキーで任意の `user_id` に書き込み可能
- **影響:** クロスユーザーデータ汚染、情報漏洩
- **修正案:** APIキーからuser_idを導出するか、user_idの所有権を検証

### C-2. メモリ検索 kinds バリデーション欠如
- **場所:** `veritas_os/api/server.py:1687`
- **問題:** `kinds` パラメータが `VALID_MEMORY_KINDS` ホワイトリストに対して未検証
- **影響:** バックエンドがstring interpolationを使用する場合のインジェクションリスク
- **修正案:** `if kind not in VALID_MEMORY_KINDS: return error` を追加

### C-3. CSPヘッダーに unsafe-inline 許可
- **場所:** `frontend/next.config.mjs:6-7`
- **問題:** `script-src 'self' 'unsafe-inline'` がインラインスクリプト実行を許可。CSPがReport-Onlyモードで未実施
- **影響:** XSS攻撃が成立する可能性
- **修正案:** nonce/hashベースに移行、Report-Onlyを外す

### C-4. Reactエラーバウンダリ未実装
- **場所:** `frontend/app/` 全ページ（console, audit, governance, risk, page.tsx）
- **問題:** エラーバウンダリコンポーネントが存在しない。任意のJS例外でページ全体がクラッシュ
- **影響:** ユーザー体験の完全な崩壊
- **修正案:** `frontend/app/error.tsx` を作成

### C-5. kernel.py のテスト完全欠如
- **場所:** `veritas_os/core/kernel.py`（テストファイルなし）
- **問題:** 意思決定の中核モジュールにユニットテストが存在しない
- **影響:** コアロジックの回帰リスク
- **修正案:** `test_kernel.py` を追加し主要パスをカバー

---

## 2. HIGH（次スプリントで対応）

### H-1. 認証失敗時のレート制限欠如
- **場所:** `veritas_os/api/server.py:703-716`
- **問題:** `require_api_key()` でAPIキー検証前にレート制限なし
- **影響:** ブルートフォース攻撃が可能
- **修正案:** IPベースの認証失敗レート制限を追加

### H-2. ゼロ除算リスク（agi_goals.py）
- **場所:** `veritas_os/core/agi_goals.py:232`
- **問題:** `normalized = {k: v / total ...}` で total=0 の場合に ZeroDivisionError
- **修正案:** `max(total, 1e-8)` を使用

### H-3. パス走査シンボリックリンク攻撃
- **場所:** `veritas_os/core/code_planner.py:70-82`
- **問題:** `resolved_p.relative_to(resolved_base)` だけではシンボリックリンク攻撃を防げない
- **修正案:** `Path.is_symlink()` チェックを明示的に追加

### H-4. ダッシュボード Nullクライアントクラッシュ
- **場所:** `veritas_os/api/dashboard_server.py:337`
- **問題:** `request.client` が None の場合（リバースプロキシ経由）、認証前にクラッシュ
- **修正案:** Null チェックを認証ロジックの前に追加

### H-5. エフェメラルパスワードのマルチワーカー競合
- **場所:** `veritas_os/api/dashboard_server.py:129-162`
- **問題:** 複数ワーカーが独立にパスワードを生成。2ワーカーで約50%の認証失敗率
- **修正案:** 共有ストレージまたは固定シードを使用

### H-6. レガシー Pickle デシリアライゼーション経路
- **場所:** `veritas_os/memory/index_cosine.py:23-47`
- **問題:** `VERITAS_MEMORY_ALLOW_LEGACY_NPZ=1` で pickle 読み込みが有効化可能（RCEリスク）
- **修正案:** レガシー pickle パスを完全削除

### H-7. debate.py リソース枯渇
- **場所:** `veritas_os/core/debate.py:378-389`
- **問題:** options リスト 100件×10フィールド×10,000文字 = 最大1MBのペイロード
- **修正案:** 総ペイロードサイズチェックを追加

### H-8. ドメインサフィックス攻撃（web_search.py）
- **場所:** `veritas_os/tools/web_search.py:584-586`
- **問題:** ホスト名の部分文字列マッチで "evilveritas.com" が "veritas.com" にマッチ
- **修正案:** 完全一致またはサブドメインチェックに修正

### H-9. LLMクライアントのAPIレスポンスログ漏洩
- **場所:** `veritas_os/core/llm_client.py:476-478`
- **問題:** APIレスポンスがwarningレベルで記録（機密情報を含む可能性）
- **修正案:** レスポンスのredactionラッパーを使用

### H-10. ハッシュチェーンのローテーション後検証不備
- **場所:** `veritas_os/logging/trust_log.py:100-138`
- **問題:** ローテーション後、マーカーファイルが欠落するとチェーンが切断
- **修正案:** チェーン切断時の警告ログと回復メカニズムを追加

### H-11. trust_log.py シンボリックリンク競合
- **場所:** `veritas_os/logging/trust_log.py:129-135`
- **問題:** symlinkチェックとunlink()の間にTOCTOU競合が存在
- **修正案:** os.replace() でアトミック操作に変更

### H-12. fetchタイムアウト欠如（フロントエンド）
- **場所:** `frontend/app/audit/page.tsx:443,480`, `frontend/app/console/page.tsx:525-535`
- **問題:** fetch呼び出しに `AbortController` タイムアウト未設定
- **修正案:** 全fetch呼び出しにタイムアウト付きAbortControllerを追加

---

## 3. MEDIUM（計画的に対応）

### M-1. CORS設定リスク
- **場所:** `veritas_os/api/server.py:500-509`
- **問題:** `["*"]` でcredentialsが有効な場合のリスク
- **修正案:** `["*"]` + credentials の組み合わせを明示的に拒否

### M-2. ガバナンスポリシーの部分更新バリデーション不足
- **場所:** `veritas_os/api/governance.py:170-200`
- **問題:** パッチの中間マージでPydanticバリデーションをバイパス可能
- **修正案:** パッチに即座にmodel_validate()を適用

### M-3. メトリクスエンドポイントの無制限ファイル一覧
- **場所:** `veritas_os/api/server.py:1750-1767`
- **問題:** SHADOW_DIR の全ファイルをページネーションなしで glob
- **修正案:** ページネーションまたは件数制限を追加

### M-4. データセット統計のOOMリスク
- **場所:** `veritas_os/logging/dataset_writer.py:309-317`
- **問題:** 最大100MBのJSONLレコードを全てリストに読み込み
- **修正案:** ストリーミング処理またはイテレータに変更

### M-5. LLMモデル名バリデーション不足
- **場所:** `veritas_os/core/llm_client.py:84-91, 429-430`
- **問題:** モデル名の検証が "../" と "/" のみ。制御文字、nullバイト未検査
- **修正案:** 既知の安全なモデル名のホワイトリスト方式に変更

### M-6. JSON再帰パースの深さ制限なし
- **場所:** `veritas_os/core/debate.py:466-512`
- **問題:** `_extract_objects_from_array()` にスタック深度制限なし
- **修正案:** 深度カウンタを追加（最大100レベル）

### M-7. クエリ長バリデーション欠如
- **場所:** `veritas_os/core/kernel_qa.py:73-135`
- **問題:** 正規表現操作前にクエリ長チェックなし
- **修正案:** `if len(q) > 10000: return None` を追加

### M-8. ワールドモデル更新のレース条件
- **場所:** `veritas_os/core/agi_goals.py:139-235`
- **問題:** 並行 decide() 呼び出しで bias_weights の競合更新
- **修正案:** ロックメカニズムを追加

### M-9. evidence.py の None チェック欠如
- **場所:** `veritas_os/core/evidence.py:54-158`
- **問題:** context["goals"] が None の場合に TypeError
- **修正案:** goals のNoneチェックを追加

### M-10. VectorMemory初期化のスレッドセーフティ
- **場所:** `veritas_os/core/memory.py:104-134`
- **問題:** `_load_model()` がロック外で実行、2スレッドで同時初期化の可能性
- **修正案:** ダブルチェックロッキングパターンを適用

### M-11. DNS解決のTOCTOU競合（web_search.py）
- **場所:** `veritas_os/tools/web_search.py:437-464`
- **問題:** DNS解決とAPI呼び出しの間にDNSリバインディング攻撃のリスク
- **修正案:** DNS解決結果をリクエスト時に再検証

### M-12. llm_safety.py ユーザー入力のプロンプト直接埋め込み
- **場所:** `veritas_os/tools/llm_safety.py:260`
- **問題:** ユーザー入力がLLMプロンプトにサニタイズなしで埋め込み
- **修正案:** 入力エスケープを追加

### M-13. useCallback メモ化欠如（governance/page.tsx）
- **場所:** `frontend/app/governance/page.tsx:298-376`
- **問題:** fetchPolicy, savePolicy, fetchValueDrift が毎レンダーで再生成
- **修正案:** useCallback でラップ

### M-14. SVG描画パフォーマンス（risk/page.tsx）
- **場所:** `frontend/app/risk/page.tsx:128-171`
- **問題:** 480個のSVG円要素が2秒ごとに全再描画
- **修正案:** Canvas/WebGLに移行、またはReact.memoを適用

### M-15. ESLint設定の不足
- **場所:** `frontend/.eslintrc.json`
- **問題:** a11y、セキュリティ、Reactベストプラクティスのルールが未設定
- **修正案:** eslint-plugin-jsx-a11y, eslint-plugin-security を追加

### M-16. .pre-commit-config.yaml の不足
- **場所:** `.pre-commit-config.yaml`
- **問題:** gitleaks のみ。ruff, bandit, black, mypy が未設定
- **修正案:** 包括的な pre-commit フックを追加

### M-17. Bandit設定の過度な除外
- **場所:** `.github/workflows/main.yml:46`
- **問題:** B101, B104, B311, B404, B603, B607 を除外（過度に寛容）
- **修正案:** 除外を最小限に絞り、代わりに個別 `# nosec` を使用

### M-18. テスト環境変数汚染
- **場所:** `veritas_os/tests/test_governance_api.py:14`
- **問題:** モジュールレベルで `os.environ["VERITAS_API_KEY"]` を設定（テスト間汚染）
- **修正案:** pytest fixture で環境変数を分離

---

## 4. LOW（改善推奨）

### L-1. config.py の空シークレット許容
- **場所:** `veritas_os/core/config.py:283-290`
- **問題:** api_secret が未設定の場合にデフォルト空文字列
- **修正案:** 起動時に非空を検証

### L-2. カリキュラムのメモリ無制限増加
- **場所:** `veritas_os/core/curriculum.py:188-194`
- **問題:** _USER_TASKS が1000ユーザーまで無制限に増加
- **修正案:** LRUキャッシュに変更

### L-3. llm_client.py の文字列結合 O(n²)
- **場所:** `veritas_os/core/llm_client.py:236-237`
- **問題:** ループ内で `extra_text += ...` による二次的なパフォーマンス劣化
- **修正案:** `list.append()` + `"".join()` に変更

### L-4. affect.py のリスト変異
- **場所:** `veritas_os/core/affect.py:173`
- **問題:** `msgs[0] = {...}` が入力リストを変更（呼び出し元に副作用）
- **修正案:** 新しいリストを返す

### L-5. 未使用変数 code_planner.py
- **場所:** `veritas_os/core/code_planner.py:261-262`
- **問題:** `_decision_count`, `_last_risk` が未使用（`# noqa: F841`）
- **修正案:** 削除またはデバッグ用途で活用

### L-6. ハードコード値の散在
- **場所:** 複数ファイル（config.py, debate.py, web_search.py 等）
- **問題:** タイムアウト（10s, 15s, 20s, 60s, 180s）、閾値が分散
- **修正案:** 設定ファイルに集約

### L-7. Dockerfileのパス問題
- **場所:** `Dockerfile:8`
- **問題:** `COPY veritas_os/requirements.txt` のパス構造が不正確な可能性
- **修正案:** パスを検証

### L-8. Docker CMD のシグナル処理
- **場所:** `Dockerfile:25`
- **問題:** CMD がexec形式でないため PID 1 のシグナル問題
- **修正案:** exec形式に変更

### L-9. エラーメッセージの不一致
- **場所:** `veritas_os/core/llm_client.py:294, 301, 310, 316`
- **問題:** 例外メッセージのフォーマットが不統一
- **修正案:** 構造化された例外フォーマットに統一

### L-10. SHA256正規表現で大文字拒否
- **場所:** `veritas_os/logging/trust_log.py:40`
- **問題:** `r"^[0-9a-f]{64}$"` が大文字16進数を拒否
- **修正案:** `re.IGNORECASE` を追加

### L-11. フロントエンドの検索レース条件
- **場所:** `frontend/app/audit/page.tsx:469-501`
- **問題:** 連続検索で応答の順序が入れ替わる可能性
- **修正案:** AbortSignalまたはリクエストカウンタを追加

### L-12. SSEストリームの再接続バックオフ
- **場所:** `frontend/components/live-event-stream.tsx:110`
- **問題:** 固定1500msリトライ（指数バックオフなし）
- **修正案:** 指数バックオフとジッターを実装

### L-13. aria-labelの不十分な記述
- **場所:** `frontend/app/audit/page.tsx:539`
- **問題:** `aria-label="request_id"` が不明瞭
- **修正案:** `aria-label="リクエストIDで検索"` に変更

### L-14. テスト乱数シードの未設定
- **場所:** `veritas_os/tests/test_thread_safety.py:28-66`
- **問題:** `np.random.rand()` にシードなし（再現性なし）
- **修正案:** `np.random.seed()` を設定

### L-15. テスト用の危険プロンプトハードコード
- **場所:** `frontend/app/console/page.tsx:18-22`
- **問題:** ジェイルブレイク試行プロンプトが本番コードに含まれる
- **修正案:** フィーチャーフラグで制御、または開発ビルドのみに限定

---

## 5. テストカバレッジ分析

### 統計
- テストファイル数: 122
- テスト関数数: 2,443
- アサーション数: 5,096
- 推定カバレッジ: 約70-75%

### テスト未実装の重要モジュール

| モジュール | 重要度 | 理由 |
|-----------|--------|------|
| `core/kernel.py` | **CRITICAL** | 意思決定の中核ロジック |
| `core/agi_goals.py` | HIGH | AGI目標と重み計算 |
| `core/pipeline.py` | HIGH | パイプラインオーケストレーション |
| `memory/embedder.py` | HIGH | ベクトル演算 |
| `scripts/doctor.py` | MEDIUM | ログ分析と検証 |
| 16+ スクリプトファイル | LOW-MEDIUM | ユーティリティスクリプト |

### 欠如しているテストカテゴリ

1. **統合テスト:** 完全な decide() フロー、API→Memory→LLM連携
2. **セキュリティテスト:** インジェクション攻撃、データプライバシー、認証バイパス
3. **エッジケーステスト:** 空入力、Unicode正規化、メモリ破損回復
4. **負荷テスト:** 大規模データセット、同時接続

---

## 6. アーキテクチャ上の懸念

### 循環依存リスク
- `kernel.py` → `affect, reason, strategy`
- `kernel_qa.py` → `kernel`（遅延インポートで回避）
- **推奨:** ツールインターフェースを分離モジュールに抽出

### ゴッドクラス
- `kernel.py`: doctor自動起動、QA処理、ツール呼び出し、パイプラインオーケストレーションを一手に担う
- `pipeline.py`: 1000行以上で複数ステージを管理
- **推奨:** コンポジションパターンで分割

### 制御の反転の欠如
- `llm_client` が Memory, Planner, Debate から直接インポート
- **推奨:** ファクトリパターンまたは依存性注入を導入

### 重複ロジック
- バイアス重み処理: `adapt.py:72-118` と `kernel_stages.py:327-333`
- **推奨:** 一方が他方を呼び出すように統合

---

## 7. ポジティブな評価点

### セキュリティ
- `secrets.compare_digest()` によるタイミングセーフ比較
- `atomic_io.py` の優れた fsync() 使用（クラッシュ安全性）
- SHA-256ハッシュチェーンの適切な実装（trust_log.py）
- 包括的なセキュリティヘッダー（CSP, X-Frame-Options, HSTS）
- パス走査防止（paths.py の体系的な検証）
- Pickle デフォルト無効化

### コード品質
- 型ヒントの一貫した使用
- Pydantic による堅牢なバリデーション（schemas.py）
- `fuji.py` の包括的なエラーコードレジストリ
- `critique.py` の適切なデフォルト値とパディングロジック
- スレッドセーフティ: RLock の一貫した使用

### フロントエンド
- サーバーサイドAPIキー管理（ブラウザに非公開）
- 型ガードによるレスポンスバリデーション
- axe-core によるアクセシビリティテスト統合
- セマンティックHTML（適切な`<section>`, `aria-label`）
- skip-to-content リンクの実装

### テスト
- `test_sanitize_pii.py`: PII検出の徹底的なテスト（615行）
- `test_thread_safety.py`: 並行性テスト（435行）
- `test_llm_client.py`: 複数プロバイダーのテスト（732行）
- `test_atomic_io.py`: アトミック操作の優れたテスト（357行）

---

## 8. 優先対応ロードマップ

### Phase 1: 即時対応（1週間以内）
1. C-1: メモリAPIのユーザー分離修正
2. C-2: kinds バリデーション追加
3. C-3: CSPヘッダーからunsafe-inline除去
4. C-4: エラーバウンダリ追加
5. H-2: agi_goals.py ゼロ除算修正
6. H-4: ダッシュボードNull クライアント修正
7. H-8: ドメインサフィックス攻撃修正

### Phase 2: 短期対応（2-4週間）
1. H-1: 認証失敗レート制限
2. H-6: レガシー pickle 経路削除
3. H-12: フロントエンド fetch タイムアウト
4. C-5: kernel.py テスト追加
5. M-5: LLMモデル名ホワイトリスト
6. M-11: DNS TOCTOU対策

### Phase 3: 中期対応（1-2ヶ月）
1. アーキテクチャ分割（kernel.py のゴッドクラス解消）
2. 循環依存の解消
3. 統合テストスイート追加
4. セキュリティテストスイート追加
5. ハードコード値の設定ファイル集約
6. .pre-commit-config の強化

---

## 総評

VERITAS OSは**セキュリティファースト**の設計思想を持ち、特にスレッドセーフティ、暗号学的監査、入力バリデーションにおいて高い品質を示しています。主要な問題は**ユーザー分離**と**フロントエンドのCSP設定**に集中しており、これらを修正すれば本番環境に適したセキュリティ体勢を確立できます。

テストカバレッジは約70-75%と推定され、特にコアモジュール（kernel.py）と統合テストの強化が必要です。アーキテクチャ面では、循環依存の解消とゴッドクラスの分割が中長期的な保守性向上に寄与します。
