# 軽量Consolidation Checkpoint 1

基準: `236a468cc426f57e70f9aad84eee1c09e9f2b5f9`（PR #2195マージ後）。
確認日: 2026-09-07。範囲を限定した静的棚卸しであり、リポジトリ全体の
未使用コード証明・セキュリティ監査・本番認証ではありません。

## 分類と扱い

| 分類 | 意味・対応 |
| --- | --- |
| KEEP | 利用される処理や独立した信頼境界。維持する。 |
| PUBLIC_COMPAT | 公開import・バージョン互換。利用側の移行確認まで維持する。 |
| TEST_ONLY | テスト基盤。変更時は収集件数とassertionを確認する。 |
| REMOVE_NEXT_MAJOR | 互換性レビュー後の将来削除案。今の削除許可ではない。 |
| DEAD | 参照・動的import・公開API・運用・復旧経路の確認が必要。今回は本体コードをこの分類に確定しない。 |

## 今回の安全な修正

同じモジュールで3つのテスト名が二重定義され、pytest収集前に前の定義が
上書きされていました。それぞれ異なる検証を含むため、削除せず改名します。

| `veritas_os/tests/`配下のファイル | 復活する前の定義の新しい名前 |
| --- | --- |
| `unit/test_kernel_decide_ext.py` | `test_decide_simple_qa_time_response_contract` |
| `integration/test_decide_e2e_ext.py` | `test_run_decide_pipeline_happy_path_with_trust_receipt` |
| `integration/test_decide_e2e_ext.py` | `test_run_decide_pipeline_explicit_options_preserve_ids_without_ml_gate` |

元のassertionはすべて維持します。復活するexplicit-optionsテストのkernel
モジュール差し替えは`monkeypatch.setitem`へ変更し、終了後に元の状態へ戻します。
後に定義されていた既存テストの名前は維持します。分類はTEST_ONLYです。
本体の認可処理・verifierは変更しません。

`tests/test_unique_test_names.py`で追跡対象pytestファイルの直接定義による
上書きを検出します。importせずASTを解析します。条件分岐内の定義、動的代入、
import名の衝突、すべてのpytest拡張を検出できるわけではありません。

対象2ファイルは194件成功。検出器のテストを含め197件成功しました。
full CIは別の確認事項であり、この件数をもって全CI成功とはしません。

## 類似テスト・ヘルパーの棚卸し

基準commitの`tests`ディレクトリ配下には追跡対象Pythonファイルが566個あります。
モジュール直下のテストをAST比較すると、位置情報を除き名前・decorator・docstring
を含めて一致するものが15グループ・38定義ありました。
例として`tests/demo/test_*_schema.py`のschema存在確認は本文が同じでも、
各モジュールの対象パスが違います。見た目の一致だけで検証を削除しません。

追跡対象の非テストPythonファイルにある、モジュール直下のヘルパー定義数:

| 名前 | 定義数 | 扱い |
| --- | ---: | --- |
| `_digest` | 50 | KEEP。AST一致は5グループ（18・5・12・2・4定義）だが参照先のglobalは異なり得る。 |
| `_timestamp` | 18 | KEEP。解析仕様とエラー契約を比較してから共通化を検討する。 |
| `_json` | 20 | KEEP。許容値・正規化の差異を確認する。 |
| `_fail` | 16 | KEEP。各領域の例外型・コードを維持する。 |

例として`policy/live_adapter_bind_authorization_codec.py`のdigestはdomainを
引数で受け取り、`policy/human_approval_requirement_resolution.py`は固有DOMAINを
使います。JSONの許容値や時刻エラー契約も異なります。名前やASTだけで
verifier・ヘルパーを統合しません。

## Legacy shim一覧

`_TARGET_MODULE`と`import_module`/`sys`による別名化のパターンに一致する
非テストファイルは39個です。以下は`veritas_os/core/`からのモジュール名で、
現時点の分類はすべてPUBLIC_COMPATです。他方式の互換層はこの抽出範囲外です。

| 区分 | モジュール名 |
| --- | --- |
| FUJI（6） | `fuji_codes`, `fuji_helpers`, `fuji_injection`, `fuji_policy`, `fuji_policy_rollout`, `fuji_safety_head` |
| Memory（14） | `memory_compliance`, `memory_distillation`, `memory_evidence`, `memory_helpers`, `memory_lifecycle`, `memory_search_helpers`, `memory_security`, `memory_storage`, `memory_store`, `memory_store_compat`, `memory_store_helpers`, `memory_summary_helpers`, `memory_vector`, `models/memory_model` |
| Pipeline（19） | `pipeline_compat`, `pipeline_contracts`, `pipeline_critique`, `pipeline_decide_stages`, `pipeline_evidence`, `pipeline_execute`, `pipeline_gate`, `pipeline_helpers`, `pipeline_inputs`, `pipeline_memory_adapter`, `pipeline_persist`, `pipeline_persistence`, `pipeline_policy`, `pipeline_replay`, `pipeline_response`, `pipeline_retrieval`, `pipeline_signature_adapter`, `pipeline_types`, `pipeline_web_adapter` |

`core/_shim_deprecation.py`にはv2.2.0・2026-08-01以降という予定がありますが、
日付の経過は移行完了の証明ではありません。`test_memory_vector_core.py`と
`test_legacy_core_shim_deprecations.py`は旧importと別名動作を検証しています。
REMOVE_NEXT_MAJORの提案には明示的なリリース判断と外部利用側の確認が必要です。

## Builder候補

ASTの名前・属性・import参照を調べると、定義ファイル外の参照がテストだけの
`build_*`が61定義あります。ただしTEST_ONLYやDEADとは判定できません。
同一ファイル内の利用、CLI、外部の公開API利用を確認する必要があります。
削除候補としなかった例:

| Builder | 根拠 | 分類 |
| --- | --- | --- |
| `audit/anchor_backends.py:build_timestamp_request` | 同一ファイル内のtimestamp要求処理から利用 | KEEP |
| `audit/trustlog_signed.py:build_trustlog_summary` | 同一ファイル内の署名監査処理から利用 | KEEP |
| `sdk/python/examples/aml_kyc_webhook_bind.py:build_review_payload` | 同一ファイル内のサンプル処理から利用 | KEEP |

残りは個別参照レビューが必要です。単語検索でも使用がない本体builderは確定
できませんでした。どちらの方法でも動的参照・外部利用までは解決できません。

## 大きいschema候補

追跡対象`*schema.json`を物理行数で並べた上位5件です。大きさはレビューの
目安であり、フィールドや埋め込み定義が不要である証拠ではありません。

| `schemas/`配下 | 行数 | UTF-8バイト数 |
| --- | ---: | ---: |
| `adapter-dry-run-fixture-result-v1.schema.json` | 6582 | 185226 |
| `adapter-dry-run-plan-v1.schema.json` | 4475 | 122180 |
| `bind-adapter-contract-selection-v1.schema.json` | 3995 | 106900 |
| `canonical-bind-preflight-adjudication-v1.schema.json` | 3087 | 81710 |
| `live-adapter-dry-run-request-v1.schema.json` | 2878 | 85831 |

分類はKEEP。生成方法・参照解決・互換性・hashや署名への影響を確認してから
整理を検討します。今回はschemaを変更しません。

## 次の境界

このテスト修正と棚卸しのレビュー後、native v2実行へ進みます。
最初の外部連携について、信頼源・時刻・変更条件・結果不明時の処理を
外部作用の接続前に固定します。正常系と障害・復旧シナリオを通した後に
freezeし、大規模Consolidation Auditを行います。1本のE2Eで未使用であることは
DEADの証明にはなりません。今回は古いPRやブランチも削除・closeしません。
