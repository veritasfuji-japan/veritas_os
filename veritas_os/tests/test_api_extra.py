#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS OS v2.0 - 追加APIエンドポイントテスト

/v1/memory, /v1/fuji/validate, /v1/metrics などの
補助エンドポイントの動作をテストします。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server


@pytest.fixture
def client(monkeypatch):
    """
    共通のTestClientセットアップ
    
    毎回APIキーを環境変数にセットし、TestClientを返します。
    """
    monkeypatch.setenv("VERITAS_API_KEY", "test-key")
    return TestClient(server.app)


# =========================
# Health / Status エンドポイント
# =========================


class TestHealthAndStatus:
    """ヘルスチェックとステータスエンドポイントのテスト"""

    def test_health_endpoint(self, client):
        """
        /health エンドポイントが正常に応答することを確認
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        body = response.json()
        
        # 必須フィールド確認
        assert body["ok"] is True
        assert isinstance(body["uptime"], int)
        assert body["uptime"] >= 0

    def test_status_endpoint(self, client):
        """
        /v1/status エンドポイントが詳細なステータスを返すことを確認
        """
        response = client.get("/v1/status")
        
        assert response.status_code == 200
        body = response.json()
        
        # 必須フィールド確認
        assert body["ok"] is True
        assert "version" in body
        assert isinstance(body["uptime"], int)
        assert body["uptime"] >= 0


# =========================
# Memory API エンドポイント
# =========================


class TestMemoryAPI:
    """MemoryOS APIのテスト"""

    def test_memory_put_and_get(self, client):
        """
        メモリの保存と取得が正常に動作することを確認
        
        /v1/memory/put → /v1/memory/get のフローをテスト
        """
        # メモリ保存
        put_payload = {
            "user_id": "test_user",
            "key": "unit_test_key",
            "value": {"foo": "bar", "count": 42},
            "kind": "semantic",
            "text": "テスト用のメモリテキスト",
            "tags": ["unit-test", "pytest"],
            "meta": {"source": "pytest", "category": "test"}
        }
        
        put_response = client.post(
            "/v1/memory/put",
            headers={"X-API-Key": "test-key"},
            json=put_payload,
        )
        assert put_response.status_code == 200
        
        put_data = put_response.json()
        assert put_data["ok"] is True
        assert put_data["legacy"]["saved"] is True
        assert put_data["legacy"]["key"] == "unit_test_key"
        
        # ベクトル保存は embedder の設定に依存するため、
        # True/False 両方を許容
        assert isinstance(put_data["vector"]["saved"], bool)

        # メモリ取得
        get_response = client.post(
            "/v1/memory/get",
            headers={"X-API-Key": "test-key"},
            json={"user_id": "test_user", "key": "unit_test_key"}
        )
        
        assert get_response.status_code == 200
        get_data = get_response.json()
        
        assert get_data["ok"] is True
        assert get_data["value"]["foo"] == "bar"
        assert get_data["value"]["count"] == 42

    def test_memory_search(self, client):
        """
        メモリ検索が正常に動作することを確認
        """
        search_payload = {
            "query": "テスト",
            "k": 5,
            "min_sim": 0.1,
            "user_id": "test_user"
        }
        
        response = client.post(
            "/v1/memory/search",
            headers={"X-API-Key": "test-key"},
            json=search_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # レスポンス構造確認
        assert data["ok"] is True
        assert isinstance(data["hits"], list)
        assert data["count"] == len(data["hits"])
        
        # ヒット件数の妥当性確認
        assert data["count"] <= search_payload["k"]

    def test_memory_put_without_optional_fields(self, client):
        """
        オプションフィールドなしでのメモリ保存をテスト
        """
        minimal_payload = {
            "user_id": "test_user",
            "key": "minimal_key",
            "value": "simple string value"
        }
        
        response = client.post(
            "/v1/memory/put",
            headers={"X-API-Key": "test-key"},
            json=minimal_payload,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


# =========================
# Trust Feedback エンドポイント
# =========================


class TestTrustFeedback:
    """Trust Feedback APIのテスト"""

    def test_trust_feedback_submission(self, client, monkeypatch):
        """
        フィードバック送信が正常に処理されることを確認
        """
        called = {}

        def fake_append_trust_log(user_id, score, note, source, extra):
            """モック関数：呼び出し引数を記録"""
            called["user_id"] = user_id
            called["score"] = score
            called["note"] = note
            called["source"] = source
            called["extra"] = extra

        # server.value_core.append_trust_log をモック化
        monkeypatch.setattr(
            server.value_core,
            "append_trust_log",
            fake_append_trust_log
        )

        # フィードバック送信
        payload = {
            "user_id": "feedback_user",
            "score": 0.9,
            "note": "テスト用フィードバック",
            "source": "unit-test"
        }
        
        response = client.post("/v1/trust/feedback", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # レスポンス確認
        assert data["status"] == "ok"
        assert data["user_id"] == "feedback_user"

        # コア関数が正しく呼ばれているか確認
        assert called["user_id"] == "feedback_user"
        assert called["score"] == 0.9
        assert called["note"] == "テスト用フィードバック"
        assert called["source"] == "unit-test"
        assert called["extra"]["api"] == "/v1/trust/feedback"

    def test_trust_feedback_with_high_score(self, client, monkeypatch):
        """
        範囲外のスコアの処理を確認
        
        注: 現在の実装ではスコアのクランプは行われず、
        そのまま記録されます
        """
        called = {}

        def fake_append_trust_log(user_id, score, note, source, extra):
            """モック関数：呼び出し引数を記録"""
            called["user_id"] = user_id
            called["score"] = score
            called["note"] = note
            called["source"] = source
            called["extra"] = extra

        monkeypatch.setattr(
            server.value_core,
            "append_trust_log",
            fake_append_trust_log
        )

        # 範囲外のスコア（1.5）
        payload = {
            "user_id": "test_user",
            "score": 1.5,
            "note": "high score test"
        }
        
        response = client.post("/v1/trust/feedback", json=payload)
        
        # 現在の実装では200を返し、スコアはそのまま記録される
        assert response.status_code == 200
        
        # スコアが記録されていることを確認（クランプなし）
        assert called["score"] == 1.5
        
        # TODO: 将来的にスコアを0-1の範囲にクランプする
        # 実装を追加することを推奨


# =========================
# FUJI Validation エンドポイント
# =========================


class TestFUJIValidation:
    """FUJI Gate 検証APIのテスト"""

    def test_fuji_validate_allow(self, client, monkeypatch):
        """
        安全なアクションがallowされることを確認
        """
        def fake_validate_action(action, context):
            """モック：安全なアクションを返す"""
            assert action == "safe_operation"
            assert context == {"environment": "test"}
            return {
                "status": "allow",
                "reasons": ["操作は安全です"],
                "violations": []
            }

        monkeypatch.setattr(
            server.fuji_core,
            "validate_action",
            fake_validate_action
        )

        response = client.post(
            "/v1/fuji/validate",
            headers={"X-API-Key": "test-key"},
            json={
                "action": "safe_operation",
                "context": {"environment": "test"}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "allow"
        assert "操作は安全です" in data["reasons"]
        assert len(data["violations"]) == 0

    def test_fuji_validate_reject(self, client, monkeypatch):
        """
        危険なアクションがrejectedされることを確認
        """
        def fake_validate_action(action, context):
            """モック：危険なアクションを返す"""
            return {
                "status": "rejected",
                "reasons": ["危険な操作です"],
                "violations": ["harm_policy"]
            }

        monkeypatch.setattr(
            server.fuji_core,
            "validate_action",
            fake_validate_action
        )

        response = client.post(
            "/v1/fuji/validate",
            headers={"X-API-Key": "test-key"},
            json={
                "action": "危険な削除操作",
                "context": {}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "rejected"
        assert len(data["violations"]) > 0


# =========================
# Metrics エンドポイント
# =========================


class TestMetrics:
    """メトリクスAPIのテスト"""

    def test_metrics_endpoint(self, client, monkeypatch, tmp_path):
        """
        メトリクスエンドポイントが正しい統計を返すことを確認
        """
        # 一時ディレクトリをセットアップ
        shadow_dir = tmp_path / "DASH"
        shadow_dir.mkdir()
        log_jsonl = tmp_path / "trust_log.jsonl"

        # パスをモック化
        monkeypatch.setattr(server, "SHADOW_DIR", shadow_dir, raising=False)
        monkeypatch.setattr(server, "LOG_JSONL", log_jsonl, raising=False)

        # テスト用のdecideファイルを作成
        decide_records = [
            {
                "request_id": f"req-{i}",
                "created_at": f"2025-01-0{i}T00:00:00Z"
            }
            for i in range(1, 4)
        ]
        
        for i, rec in enumerate(decide_records, 1):
            out = shadow_dir / f"decide_2025010{i}_000000_000.json"
            out.write_text(json.dumps(rec), encoding="utf-8")

        # テスト用のTrustLogを作成
        log_lines = ["line1\n", "line2\n", "line3\n"]
        log_jsonl.write_text("".join(log_lines), encoding="utf-8")

        # メトリクス取得
        response = client.get("/v1/metrics")
        
        assert response.status_code == 200
        data = response.json()

        # 統計確認
        assert data["decide_files"] == 3
        assert data["trust_jsonl_lines"] == 3
        assert data["server_time"].endswith("Z")  # ISO 8601形式


# =========================
# エラーハンドリング
# =========================


class TestErrorHandling:
    """エラーハンドリングのテスト"""

    def test_validation_error_422(self, client, monkeypatch):
        """
        バリデーションエラーが422を返すことを確認
        """
        # Enable debug mode to include raw_body in response
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "true")

        # min_evidenceは整数なので、文字列を入れてエラーを発生させる
        response = client.post(
            "/v1/decide",
            headers={"X-API-Key": "test-key"},
            json={"min_evidence": "not-an-int"}
        )
        
        assert response.status_code == 422
        data = response.json()

        # カスタムエラーハンドラーの出力を確認
        assert "detail" in data
        assert "hint" in data
        assert "raw_body" in data  # Only present in debug mode
        assert "expected_example" in data["hint"]

    def test_validation_error_422_no_raw_body_in_production(self, client, monkeypatch):
        """
        本番モード（デバッグ無効）では raw_body が含まれないことを確認
        """
        # Ensure debug mode is disabled
        monkeypatch.delenv("VERITAS_DEBUG_MODE", raising=False)

        response = client.post(
            "/v1/decide",
            headers={"X-API-Key": "test-key"},
            json={"min_evidence": "not-an-int"}
        )

        assert response.status_code == 422
        data = response.json()

        # Security: raw_body should NOT be present in production
        assert "detail" in data
        assert "hint" in data
        assert "raw_body" not in data

    def test_missing_api_key(self, client):
        """
        APIキー欠如が401を返すことを確認
        """
        response = client.post(
            "/v1/decide",
            # X-API-Keyなし
            json={"query": "test", "context": {"user_id": "test"}}
        )
        
        assert response.status_code == 401

    def test_invalid_api_key(self, client):
        """
        無効なAPIキーが401を返すことを確認
        """
        response = client.post(
            "/v1/decide",
            headers={"X-API-Key": "invalid-key"},
            json={"query": "test", "context": {"user_id": "test"}}
        )
        
        assert response.status_code == 401


# =========================
# パフォーマンステスト
# =========================


class TestPerformance:
    """パフォーマンス関連のテスト"""

    def test_health_check_latency(self, client):
        """
        ヘルスチェックのレイテンシが許容範囲内であることを確認
        """
        import time
        
        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # ヘルスチェックは100ms以内に応答すべき
        assert elapsed < 0.1, f"Health check took {elapsed}s (expected < 0.1s)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

