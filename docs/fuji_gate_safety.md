# FUJI Gate Safety Specification（docs/fuji_gate_safety.md）

- Version: 1.0  
- Author: VERITAS OS (藤下 + LLM Co-evolution)  
- Status: Internal Safety & Ethics Document  

---

## 1. Purpose & Scope（目的と適用範囲）

**FUJI Gate** は VERITAS OS における安全・倫理・法令遵守レイヤーである。

目的は次の 4 点：

1. 危険な decision / 実行提案 を **事前に検知・制限** する  
2. リスクの高いケースを **人間（藤下）にエスカレーション** する  
3. すべての decision に対して **一貫したリスクスコアと理由** を付与する  
4. WorldModel / DoctorReport / ログに対して **説明可能な監査トレイル** を残す  

FUJI Gate は「万能の安全装置」ではなく、  
**“制約付き AGI 研究 OS を現実世界から切り離さずに運用するための最小限のガードレール”** と位置付ける。

---

## 2. Architecture & Flow（アーキテクチャとフロー）

### 2.1 Decide パイプラインにおける位置付け

`/v1/decide` の高レベルフロー：

```text
ユーザー入力 → kernel.prepare_request()
             → FUJI.pre_check(request)    # 入力側チェック
             → planner / debate / LLM 呼び出し
             → FUJI.post_check(decision)  # 出力側チェック
             → decision_json を返す
             → world.update_from_decision()

•	pre_check:
	•	危険領域（例: 自傷・他害・違法行為の具体的手順）に近いかを判定
	•	必要に応じて 要求の再定義 / マスク / 拒否 を提案
	•	post_check:
	•	生成された decision の内容を再評価
	•	危険なステップを削除・書き換え・モデレーションノートを付与

2.2 実装インターフェース（概念）

fuji_dict = fuji.evaluate(
    request=request_json,
    draft_decision=draft_decision_json | None,
)

# 戻り値スキーマ（例）
{
    "status": "allow" | "modify" | "deny",
    "risk": 0.0 ~ 1.0,
    "reasons": [...],
    "violations": [...],
    "modifications": [...],  # 提案される修正
    "redactions": [...],     # マスクすべき情報
    "safe_instructions": [...],
}

•	status と risk は 必須
	•	kernel は status に応じて以下を行う：
	•	allow : そのまま進行
	•	modify: modifications / redactions を適用してから進行
	•	deny  : decision を返さず、safe_instructions + 警告を返す

⸻

3. Risk Model & Thresholds（リスクモデルとしきい値）

FUJI Gate は risk を 0.0〜1.0 の連続値で出力する。

仮の運用ポリシー：
	•	0.00〜0.10 : 低リスク → status = allow
	•	0.10〜0.30 : 中リスク → status = allow だが警告を付与
	•	0.30〜0.60 : 高リスク → status = modify（内容制限 or 抽象化）。必要に応じて人間レビュー推奨
	•	0.60〜1.00 : 極端リスク → status = deny ＋ セーフメッセージのみ返す

WorldModel 側では：
	•	risk >= 0.3 の decision に対しては
	•	progress_delta = 0（進捗を増やさない）
	•	場合によっては progress を減少させる（反省モード）

⸻

4. 対象ドメインと禁則事項

FUJI Gate は特に以下の領域で厳しく動作する：
	1.	自傷・他害・犯罪行為の具体的助言
	2.	違法行為や規約違反を前提とした自動化（例: 不正アクセス）
	3.	センシティブな個人情報の収集・推測・拡散
	4.	医療・法律・金融など高リスク領域での、専門家なしの決定代行
	5.	差別・ヘイト・誹謗中傷の助長
	6.	VERITAS 自身の制御を失わせる操作（自己削除・鍵漏洩など）

これらの要求に対しては、FUJI Gate は原則 status = deny とし、
代わりに「安全な代替案」や「専門家への相談」を返す。

⸻

5. 主要な失敗モードと対策（10件以上）

5.1 想定失敗モード
	1.	設計暴走
	•	Planner が自己複雑化し、どんな要求にも巨大な計画を返す
	•	progress が毎回増え続け、常に「前進しているように見える」
	2.	ログ破損
	•	world_state.json / doctor_report.json がパース不能になる
	•	リスク情報や過去 decision へのリンクが失われる
	3.	状態不整合
	•	progress が 1.0 を超える / 負の値になる
	•	decision_count が急にリセットされる
	4.	FUJI Gate 無効化
	•	バグや設定ミスで fuji.status が常に allow になる
	•	高リスク decision が素通りする
	5.	リスク過小評価
	•	実際は危険な内容でも risk <= 0.05 と判定され続ける
	•	ValueCore / テストケースの偏りによって起こる
	6.	decision_latency 異常増加
	•	安全チェックがボトルネックになり、毎回数十秒かかる
	•	実用性が落ち、人間が FUJI を無効化しようとする動機になる
	7.	メトリクスロギング停止
	•	decision_count は増えるが metrics が更新されない
	•	後からリスク分析できなくなる
	8.	progress 過大評価
	•	実装を伴わない「考察だけ」で progress が大きく上がる
	•	現実のコードベースとのギャップが広がる
	9.	人間レビュー抜け
	•	高リスク decision が allow で通り続け、
「人間が一度も内容を見ていない」状態でシステムが進化する
	10.	API スキーマ変更への未対応
	•	kernel.decide() や LLM API のレスポンス形式変更に追随できず、
FUJI Gate が誤動作・クラッシュする
	11.	バックアップ／スナップショット喪失
	•	Drive 同期や zip バックアップが長期間失敗し、
誤った自己改善をロールバックできなくなる

5.2 対策・検知シグナル

各失敗モードに対する代表的な対策：
	•	設計暴走
	•	planner.steps の平均長・分布を監視
	•	閾値超えで DoctorReport に警告を記録
	•	ログ破損 / 状態不整合
	•	読み込み時にスキーマバリデーションを必須化
	•	失敗時は直近の world_state_*.bak から復旧
	•	FUJI 無効化 / リスク過小評価
	•	一定期間 risk < 0.01 が続くと警告
	•	テストベンチ（攻めたプロンプト）で FUJI を定期チェックする
	•	人間レビュー抜け
	•	risk >= 0.3 の decision を別ファイルへ抽出
	•	週次で藤下がざっと目を通す「FUJI Review」スロットを確保
	•	バックアップ喪失
	•	backup_logs.sh 実行結果を DoctorReport に記録
	•	7日以上バックアップがなければアラート

⸻

6. ログ設計と監査（Auditability）

FUJI Gate の出力は各 decision ログに埋め込まれる：

"fuji": {
  "status": "allow",
  "risk": 0.05,
  "reasons": [...],
  "violations": [],
  "modifications": [],
  "redactions": [],
  "safe_instructions": []
}
	•	WorldModel
	•	last_risk に fuji.risk を反映し、
長期的な安全トレンドを可視化する
	•	DoctorReport
	•	リスクの高い decision を集約し、
「どの領域で危険な要求が多いか」を俯瞰する
	•	Benchmarks
	•	ベンチ実行時も FUJI のログを残し、
攻めた AGI ベンチが安全に動作しているか確認できる

⸻

7. Human-in-the-loop ポリシー

FUJI Gate は 最終的な責任主体を人間に残す 前提で設計する。
	•	risk >= 0.3 の decision は「要レビュー」とみなし、
週次〜隔週レベルで藤下がまとめて確認する
	•	ValueCore の値調整や、
risk 閾値の変更など ポリシーレベルの編集 は必ず人間が行う
	•	VERITAS 自身が「FUJI の設定を変えたい」と提案する場合も、
その適用は人間レビュー後に手動で行う

⸻

8. Limitations & Roadmap（限界と今後）

8.1 現状の限界
	•	リスク判定は LLM ベースであり、完璧ではない
	•	法域（国ごとの法律）を完全にはカバーできない
	•	「長期的な価値観の歪み」（ゆっくり偏った判断を学習する）の検知は弱い

8.2 今後の拡張案（Step3〜Step5 で検討）
	1.	FUJI 用の テストベンチ（危険プロンプト集）を作成し、
リリース前に自動チェックする
	2.	リスク判定ロジックを ルールベース + LLM のハイブリッドにする
	3.	WorldModel と連携し、「高リスク decision のクラスター分析」を行う
	4.	一定閾値を超えた場合は自動的に self-heal / safe-mode へ移行する

