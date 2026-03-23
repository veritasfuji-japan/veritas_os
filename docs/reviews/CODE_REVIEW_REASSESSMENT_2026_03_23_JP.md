# VERITAS OS 再評価レビュー（2026-03-23）

## 目的

`docs/reviews/CODE_REVIEW_2026_03_21_JP.md` を全文読了した上で、現行コードベースと主要ドキュメントを再確認し、**2026-03-23 時点の再評価**を行った。

今回の再評価では、特に以下を重点確認した。

- Planner / Kernel / FUJI / MemoryOS の責務境界が維持されているか
- `/v1/decide` 周辺の orchestrator 分離が実装で保たれているか
- startup / health / status 系で fail-open の残存経路がどこまで縮小されたか
- Memory 劣化や監査ログ劣化が observability 上で可視化されているか
- ドキュメント記述と現行実装の整合性にズレがないか

---

## 再評価サマリー

結論として、**2026-03-21 レビューで指摘されていた主要な P0/P1 領域はかなり前進している**。

特に良い点は次のとおりである。

1. `pipeline.py` が「単一エントリポイント + orchestration 専用」であることを強く宣言し、実際に stage モジュールへ処理を委譲している。
2. `routes_system.py` が health / status で `runtime_features`、`auth_store`、`trust_log`、`memory_health` を返し、silent degradation をかなり潰している。
3. `startup_health.py` が production で sanitize 欠落・atomic I/O 欠落・auth fail-open 要求を fail-closed に寄せている。
4. `memory/store.py` が non-fatal な読み込み失敗を `issue_code` ベースで記録し、empty-state fallback の監視可能性を補強している。

一方で、**設計品質は高いが、運用上はまだ「複雑さそのもの」が主要リスク**である。

- Kernel / Planner は責務境界の方針こそ適切だが、依然として大きく、互換レイヤも残る。
- health/status で可視化は進んだ一方、監視側が新フィールドを実際にアラートに結びつけなければ意味が薄い。
- ドキュメント間には一部の古い表現が残っており、運用者や新規開発者に誤解を与える余地がある。

---

## 総合評価（再評価）

- **設計品質**: 高い
- **責務分離**: 良好。前回評価より改善が明確
- **監査性 / 可観測性**: 良好。degraded 状態の露出が強化された
- **セキュリティ姿勢**: 高い。特に production fail-closed が明文化された
- **保守性**: 良いが、Kernel / Planner / 互換レイヤの複雑性は引き続き課題
- **運用成熟度**: ベータとして堅実。ただし README 間のメッセージ差異に注意

総評として、現状の VERITAS OS は**「fail-closed を志向する監査型 Decision OS」として一貫性が増した**と評価できる。

---

## 2026-03-21 レビューから改善が確認できた点

### 1. Pipeline の責務分離は、方針だけでなくコード形状にも反映されている

`veritas_os/core/pipeline.py` は、公開契約として `run_decide_pipeline(req, request)` を単一エントリポイントと定義し、input / execute / policy / response / persist / replay を専用モジュールへ委譲する方針を docstring で明示している。

これは単なるコメントではなく、実際に `pipeline_inputs`、`pipeline_execute`、`pipeline_policy`、`pipeline_response`、`pipeline_persist`、`pipeline_replay` を import して orchestrate する構造になっているため、前回レビューの「pipeline 分割の方向性が良い」という評価は、**方向性ではなく定着段階に入った**と見てよい。

### 2. health / status が degraded state を表現できるようになった

`veritas_os/api/routes_system.py` では、`/health` と `/status` 系が単なる `ok: true/false` ではなく、`status`、`checks`、`runtime_features`、`auth_store`、`trust_log`、`memory_health` を返す。

これは前回レビューで懸念された以下を直接補強している。

- sanitize 欠落
- atomic I/O 欠落
- auth store の degradation
- trust log 集約 JSON の unreadable / invalid 化
- MemoryStore の empty-state fallback

特に良いのは、`pipeline` や `memory` の unavailable と、runtime / auth / trust log の degraded を分けている点で、**停止系障害と安全機能劣化を区別できる**ことである。

### 3. startup hardening が production で fail-closed に寄っている

`veritas_os/api/startup_health.py` は、以下を production で起動拒否対象として扱う。

- `sanitize` 未ロード
- `atomic_io` 未ロード
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true`
- `VERITAS_AUTH_STORE_FAILURE_MODE=open`
- `NEXT_PUBLIC_VERITAS_API_BASE_URL` の設定

これにより、前回レビューの「可用性優先で fail-open 気味」という指摘は、少なくとも startup gate の観点ではかなり縮小された。特に `VERITAS_ENV=prod` と `production` の両方を production とみなす設計は、環境別名による取りこぼしを減らしており実務的である。

### 4. Memory の silent degradation が telemetry 化された

`veritas_os/memory/store.py` は、JSON decode error や `FileNotFoundError`、`PermissionError` などを `_record_load_issue()` で記録し、`health_snapshot()` で取得できる。

また `_classify_load_exception()` が `file_missing` / `permission_denied` / `io_error` を返すため、前回レビューで問題視されていた「破損・消失・I/O 障害の区別が上位から見えにくい」という点は大きく改善している。

これは observability の改善として高く評価できる。

---

## 現時点で強く評価できる設計上の長所

### 1. 責務境界の維持が README と実装の両方で一貫している

トップレベル `README_JP.md` では Planner / Kernel / FUJI / MemoryOS それぞれの「主責務」「持ち込むべきでない責務」「推奨拡張方向」が明示されている。

さらに実装でも、

- `pipeline.py` は orchestration に寄せる
- `kernel.py` は decision computation を責務とする
- `planner.py` は helper/normalization 分離を進める

という形で、境界が少なくとも文書レベルのスローガンで終わっていない。

この点は、ユーザーのカスタム指示にある**「Planner / Kernel / Fuji / MemoryOS の責務を越える変更は禁止」**という制約とも整合的である。

### 2. 互換性維持のやり方が比較的健全

`pipeline.py` と `kernel.py` の docstring は、互換ラッパーの存在を認めつつ、**新規の分岐や fallback shaping は helper/stage 側へ寄せるべき**と宣言している。

これは大規模リファクタリング時にありがちな「互換のために本体が再肥大化する」失敗を抑える指針として有効である。

### 3. セキュリティ警告がコードに埋め込まれている

`startup_health.py` や `memory/store.py` では、危険設定や production で不正なパスを logger warning / RuntimeError で明示している。

単に安全な実装にするだけでなく、**運用時の誤設定が観測可能になるよう設計している**点は優秀である。

---

## 追加で見えた懸念点

### 1. 最大の敵は「責務逸脱」より「複雑性の再流入」

前回レビューは Planner / Kernel の重さを懸念していたが、この懸念はまだ有効である。

`kernel.py` は docstring 上は責務が明確でも、依然として import 対象・互換配慮・安全機構・QA helper 連携が多い。`planner.py` も helper 分離は進んでいるが、本体はまだ十分に軽いとは言いがたい。

したがって今後の最大リスクは、Planner が Kernel 化したり、Kernel が Pipeline / API 側の判断を再吸収したりするような**責務越境の再発**よりも、**既に許容している互換レイヤや例外吸収の周辺にロジックが再流入すること**である。

### 2. 可観測性は改善したが、監視契約としてはまだ要運用設計

`routes_system.py` は degraded 情報を返すが、これだけでは十分ではない。

運用上の本当の問いは以下である。

- `status=degraded` を本当にアラート対象にしているか
- `checks.auth_store=degraded` と `checks.memory=degraded` を同列に扱ってよいか
- `runtime_features.sanitize=degraded` を即時 Sev1 と見なすか
- `trust_log.status=degraded` を write path 停止条件にするか

つまり、**API が返すだけでは監査性は完成しない**。監視・SLO・runbook がその契約を吸収して初めて強い。

### 3. ドキュメントの世代差がやや大きい

トップレベル `README_JP.md` は「ベータ品質のガバナンス基盤」として慎重なトーンで記載している。一方、`veritas_os/README_JP.md` では `Production Ready (98%)` バッジや古い構成説明が残っており、現行トップレベル README と比べるとメッセージが強すぎる。

この差はコードの脆弱性ではないが、**運用期待値のミスリード**になりうる。

特に外部説明・顧客説明・監査説明では、どの README を正として扱うかを曖昧にしない方がよい。

### 4. Memory directory の production fallback は安全だが、誤設定修復を遅らせる可能性がある

`memory/store.py` は production で `VERITAS_MEMORY_DIR` が allowlist に合わなければ default path へ fallback する。これは安全側の設計として妥当である。

ただし運用的には、「意図した永続領域を使えていないのに起動してしまう」ため、場合によっては warning ではなく**より強い health degradation 表示**や deployment-time 検証強化があってもよい。

これはセキュリティ脆弱性というより、**設定不備の長期潜伏リスク**である。

---

## セキュリティ警告

### 警告 1. degraded を検知しても自動隔離しない限り、運用上は fail-open に近づく

health/status/metrics の可視化は大きく改善しているが、監視設定が弱いと「degraded が見えているだけ」で稼働を続けることになる。

これはコード欠陥ではないが、**運用設計が追いつかなければ結果として fail-open 的な運用**になる。

### 警告 2. `veritas_os/README_JP.md` の強い readiness 表現は、セキュリティ期待値の誤設定を招く可能性がある

現行トップレベル README が「ベータ」と整理しているのに対し、別 README が強い production-ready 表現を残している点は、利用者に「未整備の運用前提まで既に充足されている」と誤認させるリスクがある。

これは直接的なコード脆弱性ではないが、**安全な導入判断を誤らせるドキュメントリスク**として注意が必要である。

### 警告 3. Memory path fallback はデータ配置ミスの発見を遅らせる可能性がある

production で allowlist 不一致時に default path へ退避する設計は安全寄りだが、期待していた保護領域や永続ボリュームを使えていない場合、後から気づくと監査・保持・災害復旧の観点で問題になる。

必要であれば、より厳しい profile ではここも fail-closed を検討すべきである。

---

## 優先度つき提案（再評価版）

### P1: ドキュメントの正本をさらに明確化する

- トップレベル `README_JP.md` を正本とするなら、`veritas_os/README_JP.md` にその旨をより強く書く
- `Production Ready (98%)` のような強い表現は、現行の beta positioning と整合する形へ弱める
- review 文書マップから「どの README / review が最新の運用判断に使う文書か」を見つけやすくする

### P1: degraded の運用意味を runbook / alert policy に固定する

- `sanitize=degraded`、`atomic_io=degraded`、`auth_store=degraded`、`memory=degraded` の優先度差を運用文書で固定する
- `/health` と `/status` の `status=degraded` をアラートにする条件を文書化する
- SLO/SLI と結びつけて「いつ再起動・隔離・リリース停止するか」を明文化する

### P2: Kernel / Planner の複雑性メトリクスを CI 管理する

- ファイル長
- public function 数
- compatibility wrapper 数
- stage/helper 依存方向

などを定量化し、責務逸脱より前に**複雑性上限超過**を検知できるようにするとよい。

### P2: production profile の Memory path 誤設定をより強く露出する

- `memory_health` に configuration mismatch を載せる
- もしくは deployment checker で `VERITAS_MEMORY_DIR` と allowlist 不一致を静的に検知する

これにより、fallback 自体は維持しても、誤設定が埋もれにくくなる。

---

## 最終結論

2026-03-23 時点の再評価では、VERITAS OS は前回レビュー時点よりも明確に改善しており、特に以下が強い。

- **責務分離の実装定着**
- **production fail-closed の強化**
- **silent degradation の health/status 露出**
- **Memory 障害の telemetry 化**

したがって本システムは、単なる研究用プロトタイプではなく、**監査・安全・責務境界を重視したベータ品質の Decision OS**としてかなり整理されている。

ただし、今後の主要課題は「新しい安全機能の追加」そのものよりも、

1. 複雑性の再流入を防ぐこと
2. degraded state を運用上の実アクションへ結びつけること
3. ドキュメントの正本性と期待値を統一すること

の3点である。

以上より、再評価の判定は次のとおりとする。

- **アーキテクチャ再評価**: 良好
- **セキュリティ再評価**: 良好。ただし運用監視設計が前提
- **運用成熟度再評価**: ベータとして高い
- **総合判定**: **前回レビューより改善、ただし複雑性管理と運用契約の明文化が次の主戦場**
