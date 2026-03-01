#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS OS v2.0 - Dataset Writer テスト

dataset_writer.py モジュールの機能をテストします：
- レコード生成
- バリデーション
- JSONL追記
- 統計取得
- 検索機能
"""

from pathlib import Path
import json
import tempfile
from datetime import datetime, timezone

import pytest

from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    validate_record,
    append_dataset_record,
    get_dataset_stats,
    search_dataset,
)
from veritas_os.core.decision_status import DecisionStatus


# =========================
# テスト用データ生成ヘルパー
# =========================


def create_dummy_request():
    """ダミーリクエストペイロードを生成"""
    return {
        "query": "テスト用クエリ",
        "context": {
            "user_id": "test_user",
            "session_id": "test_session",
            "goals": ["効率性", "安全性"],
            "constraints": ["時間制約"]
        }
    }


def create_dummy_response(status="allow", memory_used=True):
    """ダミーレスポンスペイロードを生成"""
    return {
        "chosen": {
            "id": "opt1",
            "title": "選択肢1",
            "description": "テスト用の選択肢",
            "score": 0.9,
            "world": {
                "utility": 0.8,
                "predicted_risk": 0.1,
                "predicted_benefit": 0.9,
                "predicted_cost": 0.2
            }
        },
        "alternatives": [
            {
                "id": "opt2",
                "title": "選択肢2",
                "description": "代替案",
                "score": 0.7
            }
        ],
        "evidence": [
            {
                "source": "memory",
                "confidence": 0.95,
                "snippet": "過去の類似事例",
                "uri": "memory://episode_123"
            },
            {
                "source": "web_search",
                "confidence": 0.85,
                "snippet": "外部情報源",
                "uri": "https://example.com/article"
            }
        ],
        "fuji": {
            "status": "ok",
            "reasons": ["ポリシー違反なし"],
            "violations": []
        },
        "gate": {
            "decision_status": status,
            "risk": 0.1,
            "telos_score": 0.8,
            "reason": "安全な操作"
        },
        "memory": {
            "used": memory_used,
            "citations": 3 if memory_used else 0
        }
    }


def create_dummy_meta():
    """ダミーメタデータを生成"""
    return {
        "api_version": "v2.0",
        "kernel_version": "2.0.0",
        "server": "test-server",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =========================
# レコード生成テスト
# =========================


class TestBuildDatasetRecord:
    """build_dataset_record 関数のテスト"""

    def test_basic_record_creation(self):
        """基本的なレコード生成が正常に動作することを確認"""
        req = create_dummy_request()
        res = create_dummy_response()
        meta = create_dummy_meta()

        record = build_dataset_record(req, res, meta)

        # 必須フィールドの存在確認
        assert "ts" in record
        assert "request" in record
        assert "response" in record
        assert "labels" in record
        assert "meta" in record
        assert "version" in record

    def test_request_section(self):
        """requestセクションが正しく生成されることを確認"""
        req = create_dummy_request()
        res = create_dummy_response()
        meta = create_dummy_meta()

        record = build_dataset_record(req, res, meta)
        request = record["request"]

        # リクエスト内容確認
        assert "payload" in request
        assert "hash" in request
        assert request["payload"]["query"] == "テスト用クエリ"

    def test_response_section(self):
        """responseセクションが正しく生成されることを確認"""
        req = create_dummy_request()
        res = create_dummy_response()
        meta = create_dummy_meta()

        record = build_dataset_record(req, res, meta)
        response = record["response"]

        # レスポンス内容確認
        assert "chosen" in response
        assert "alternatives" in response
        assert "evidence" in response
        assert "fuji" in response
        assert "gate" in response
        assert "memory" in response

        # chosenの詳細確認
        chosen = response["chosen"]
        assert chosen["id"] == "opt1"
        assert chosen["score"] == 0.9
        assert "utility" in chosen

    def test_labels_section(self):
        """labelsセクションが正しく生成されることを確認"""
        req = create_dummy_request()
        res = create_dummy_response(status="allow", memory_used=True)
        meta = create_dummy_meta()

        record = build_dataset_record(req, res, meta)
        labels = record["labels"]

        # ラベルの内容確認
        assert labels["status"] == "allow"
        assert labels["fuji_status"] == "ok"
        assert labels["blocked"] is False
        assert labels["memory_used"] is True
        assert labels["memory_citations"] == 3

    def test_decision_status_normalization(self):
        """DecisionStatus が正しく正規化されることを確認"""
        req = create_dummy_request()
        
        # 各ステータスをテスト
        statuses = ["allow", "modify", "rejected"]
        
        for status in statuses:
            res = create_dummy_response(status=status)
            meta = create_dummy_meta()
            
            record = build_dataset_record(req, res, meta)
            
            assert record["labels"]["status"] == status
            assert record["labels"]["blocked"] == (status == "rejected")


    def test_memory_citations_negative_value_is_sanitized(self):
        """memory citations の負数が 0 に正規化されることを確認"""
        req = create_dummy_request()
        res = create_dummy_response(memory_used=True)
        res["memory"]["citations"] = -5
        meta = create_dummy_meta()

        record = build_dataset_record(req, res, meta)

        assert record["labels"]["memory_citations"] == 0
        assert record["response"]["memory"]["citations"] == 0

    def test_memory_usage_tracking(self):
        """メモリ使用状況が正しく記録されることを確認"""
        req = create_dummy_request()
        meta = create_dummy_meta()
        
        # メモリ使用あり
        res_with_memory = create_dummy_response(memory_used=True)
        record_with = build_dataset_record(req, res_with_memory, meta)
        
        assert record_with["labels"]["memory_used"] is True
        assert record_with["labels"]["memory_citations"] == 3
        
        # メモリ使用なし
        res_without_memory = create_dummy_response(memory_used=False)
        record_without = build_dataset_record(req, res_without_memory, meta)
        
        assert record_without["labels"]["memory_used"] is False
        assert record_without["labels"]["memory_citations"] == 0


# =========================
# バリデーションテスト
# =========================

class TestValidateRecord:
    """validate_record 関数のテスト"""

    def test_valid_record(self):
        """正しいレコードがバリデーションを通過することを確認"""
        req = create_dummy_request()
        res = create_dummy_response()
        meta = create_dummy_meta()
        
        record = build_dataset_record(req, res, meta)
        valid, error = validate_record(record)
        
        assert valid is True
        assert error is None

    def test_missing_required_fields(self):
        """必須フィールド欠如がバリデーションエラーになることを確認"""
        # 不完全なレコード
        invalid_record = {
            "ts": 1234567890000,
            # "request" がない
            "response": {},
            "labels": {}
        }
        
        valid, error = validate_record(invalid_record)
        
        assert valid is False
        assert error is not None
        assert "request" in error.lower()

    def test_invalid_timestamp(self):
        """無効なタイムスタンプがエラーになることを確認"""
        req = create_dummy_request()
        res = create_dummy_response()
        meta = create_dummy_meta()
        
        record = build_dataset_record(req, res, meta)
        record["ts"] = "invalid_timestamp"
        
        valid, error = validate_record(record)
        
        assert valid is False


# =========================
# JSONL追記テスト
# =========================


class TestAppendDatasetRecord:
    """append_dataset_record 関数のテスト"""

    def test_append_single_record(self):
        """単一レコードの追記が正常に動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            req = create_dummy_request()
            res = create_dummy_response()
            meta = create_dummy_meta()
            
            record = build_dataset_record(req, res, meta)
            append_dataset_record(record, path=path, validate=True)
            
            # ファイルが作成されたことを確認
            assert path.exists()
            
            # 内容を確認
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            assert len(lines) == 1
            loaded = json.loads(lines[0])
            assert loaded["request"]["payload"]["query"] == "テスト用クエリ"

    def test_append_multiple_records(self):
        """複数レコードの追記が正常に動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 5件のレコードを追記
            for i in range(5):
                req = create_dummy_request()
                req["query"] = f"クエリ{i}"
                res = create_dummy_response()
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # 5件すべてが記録されているか確認
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            assert len(lines) == 5

    def test_append_with_validation_error(self):
        """
        バリデーションエラー時の動作を確認
        
        注: 現在の実装では validate=True の場合、
        バリデーションエラー時はファイルに書き込まれません
        （エラーログのみ出力）
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 不正なレコード
            invalid_record = {"invalid": "record"}
            
            # バリデーションエラー時は書き込まれない
            append_dataset_record(
                invalid_record,
                path=path,
                validate=True
            )
            
            # ファイルは作成されない（バリデーションエラーのため）
            assert not path.exists() or path.stat().st_size == 0
            
            # validate=False の場合は書き込まれる
            append_dataset_record(
                invalid_record,
                path=path,
                validate=False
            )
            
            assert path.exists()
            assert path.stat().st_size > 0

    def test_append_without_validation(self):
        """バリデーションなしの追記が動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 不完全なレコードでもvalidate=Falseなら追記可能
            record = {"test": "data"}
            append_dataset_record(record, path=path, validate=False)
            
            assert path.exists()


# =========================
# 統計取得テスト
# =========================


class TestGetDatasetStats:
    """get_dataset_stats 関数のテスト"""

    def test_basic_statistics(self):
        """基本統計が正しく計算されることを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 複数のステータスのレコードを作成
            statuses = ["allow", "allow", "modify", "rejected"]
            
            for status in statuses:
                req = create_dummy_request()
                res = create_dummy_response(status=status)
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # 統計取得
            stats = get_dataset_stats(path=path)
            
            # 基本統計確認
            assert stats["total_records"] == 4
            assert stats["status_counts"]["allow"] == 2
            assert stats["status_counts"]["modify"] == 1
            assert stats["status_counts"]["rejected"] == 1

    def test_memory_usage_statistics(self):
        """メモリ使用統計が正しく計算されることを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # メモリ使用あり/なしのレコードを作成
            for memory_used in [True, True, True, False, False]:
                req = create_dummy_request()
                res = create_dummy_response(memory_used=memory_used)
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            stats = get_dataset_stats(path=path)
            
            assert stats["memory_usage"]["used"] == 3
            assert stats["memory_usage"]["unused"] == 2

    def test_score_statistics(self):
        """スコア統計が正しく計算されることを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            scores = [0.9, 0.8, 0.7, 0.6, 0.5]
            
            for score in scores:
                req = create_dummy_request()
                res = create_dummy_response()
                res["chosen"]["score"] = score
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            stats = get_dataset_stats(path=path)
            
            # 平均スコア確認
            expected_avg = sum(scores) / len(scores)
            assert abs(stats["avg_score"] - expected_avg) < 0.01

    def test_empty_dataset_statistics(self):
        """空のデータセットに対する統計が正しく返されることを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            path.touch()  # 空ファイル作成
            
            stats = get_dataset_stats(path=path)
            
            assert stats["total_records"] == 0
            assert stats["status_counts"] == {}
            assert stats["avg_score"] == 0.0

    def test_statistics_ignore_invalid_json_lines(self):
        """不正なJSON行を無視して統計集計を継続することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"

            valid_record = build_dataset_record(
                create_dummy_request(),
                create_dummy_response(status="allow", memory_used=True),
                create_dummy_meta(),
            )
            append_dataset_record(valid_record, path=path, validate=True)

            with path.open("a", encoding="utf-8") as f:
                f.write("{invalid json line}\n")

            append_dataset_record(
                build_dataset_record(
                    create_dummy_request(),
                    create_dummy_response(status="modify", memory_used=False),
                    create_dummy_meta(),
                ),
                path=path,
                validate=True,
            )

            stats = get_dataset_stats(path=path)

            assert stats["total_records"] == 2
            assert stats["status_counts"]["allow"] == 1
            assert stats["status_counts"]["modify"] == 1
            assert stats["memory_usage"]["used"] == 1
            assert stats["memory_usage"]["unused"] == 1

    def test_statistics_return_file_too_large_error(self, monkeypatch):
        """サイズ上限を超える場合に file_too_large を返すことを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            append_dataset_record(
                build_dataset_record(
                    create_dummy_request(),
                    create_dummy_response(),
                    create_dummy_meta(),
                ),
                path=path,
                validate=True,
            )

            monkeypatch.setattr(
                "veritas_os.logging.dataset_writer.MAX_DATASET_STATS_SIZE",
                1,
            )

            stats = get_dataset_stats(path=path)

            assert stats["total_records"] == -1
            assert stats["error"] == "file_too_large"


# =========================
# 検索機能テスト
# =========================


class TestSearchDataset:
    """search_dataset 関数のテスト"""

    def test_search_by_query(self):
        """クエリによる検索が正常に動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 異なるクエリのレコードを作成
            queries = ["天気予報", "交通情報", "ニュース"]
            
            for query in queries:
                req = create_dummy_request()
                req["query"] = query
                res = create_dummy_response()
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # "天気"を含むレコードを検索
            results = search_dataset(query="天気", path=path)
            
            assert len(results) == 1
            assert "天気" in results[0]["request"]["payload"]["query"]

    def test_search_by_status(self):
        """ステータスによるフィルタリングが正常に動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            statuses = ["allow", "allow", "modify", "rejected"]
            
            for status in statuses:
                req = create_dummy_request()
                res = create_dummy_response(status=status)
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # allowステータスのみ検索
            results = search_dataset(status="allow", path=path)
            assert len(results) == 2
            
            # rejectedステータスのみ検索
            results = search_dataset(status="rejected", path=path)
            assert len(results) == 1

    def test_search_by_memory_used(self):
        """メモリ使用フラグによるフィルタリングが動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            for memory_used in [True, True, False, False, False]:
                req = create_dummy_request()
                res = create_dummy_response(memory_used=memory_used)
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # メモリ使用ありのみ検索
            results = search_dataset(memory_used=True, path=path)
            assert len(results) == 2
            
            # メモリ使用なしのみ検索
            results = search_dataset(memory_used=False, path=path)
            assert len(results) == 3

    def test_search_with_limit(self):
        """limit パラメータが正しく動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 10件のレコードを作成
            for i in range(10):
                req = create_dummy_request()
                res = create_dummy_response()
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # limit=5で検索
            results = search_dataset(path=path, limit=5)
            
            assert len(results) == 5

    def test_search_with_non_positive_limit(self, tmp_path):
        """limit が 0 以下の場合は空配列を返すことを確認"""
        dataset_path = tmp_path / "dataset.jsonl"
        dataset_path.write_text(
            '{"ts":1,"request":{"payload":{"query":"q"}},"response":{"chosen":{"score":0.5}},"labels":{"status":"allow","memory_used":false}}\n',
            encoding="utf-8",
        )

        assert search_dataset(limit=0, path=dataset_path) == []
        assert search_dataset(limit=-1, path=dataset_path) == []

    def test_search_combined_filters(self):
        """複数フィルタの組み合わせが正しく動作することを確認"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 様々な組み合わせのレコードを作成
            configs = [
                ("allow", True),
                ("allow", False),
                ("modify", True),
                ("rejected", False)
            ]
            
            for status, memory_used in configs:
                req = create_dummy_request()
                res = create_dummy_response(
                    status=status,
                    memory_used=memory_used
                )
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # allow + memory_used=True の組み合わせ検索
            results = search_dataset(
                status="allow",
                memory_used=True,
                path=path
            )
            
            assert len(results) == 1


# =========================
# 統合テスト
# =========================


class TestDatasetWriterIntegration:
    """Dataset Writer の統合テスト"""

    def test_full_workflow(self):
        """レコード生成→追記→統計→検索の完全なワークフローをテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dataset.jsonl"
            
            # 1. 複数レコードの生成と追記
            for i in range(10):
                req = create_dummy_request()
                req["query"] = f"テストクエリ{i}"
                
                status = ["allow", "modify", "rejected"][i % 3]
                memory_used = (i % 2 == 0)
                
                res = create_dummy_response(
                    status=status,
                    memory_used=memory_used
                )
                meta = create_dummy_meta()
                
                record = build_dataset_record(req, res, meta)
                append_dataset_record(record, path=path, validate=True)
            
            # 2. 統計取得
            stats = get_dataset_stats(path=path)
            assert stats["total_records"] == 10
            
            # 3. 検索実行
            allow_results = search_dataset(status="allow", path=path)
            assert len(allow_results) > 0
            
            memory_results = search_dataset(memory_used=True, path=path)
            assert len(memory_results) == 5  # 偶数インデックス


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

