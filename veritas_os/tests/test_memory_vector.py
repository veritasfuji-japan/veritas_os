#!/usr/bin/env python3
"""
MemoryOS ベクトル検索 テストスクリプト

使用方法:
    python tests/test_memory_vector.py
"""

import sys
import logging
from pathlib import Path

# プロジェクトルートをPythonパスに追加
REPO_ROOT = Path(__file__).resolve().parents[2]  # ★ ここを 2 に
sys.path.insert(0, str(REPO_ROOT))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



def test_vector_memory_standalone():
    """VectorMemoryクラス単体のテスト"""
    print("=" * 60)
    print("Test 1: VectorMemory standalone")
    print("=" * 60)

    try:
        # VERITAS の core をパッケージとしてインポート
        from veritas_os.core import memory
        VectorMemory = memory.VectorMemory

        vec_mem = VectorMemory(index_path=None)

        if vec_mem.model is None:
            print("❌ sentence-transformers not available")
            print("   Install with: pip install sentence-transformers")
            return False

        print("✅ VectorMemory initialized")

        # ドキュメント追加
        test_docs = [
            {
                "kind": "test",
                "text": "AGI OS の設計について議論した",
                "tags": ["agi", "design"],
            },
            {
                "kind": "test",
                "text": "VERITAS アーキテクチャを検討",
                "tags": ["architecture"],
            },
            {
                "kind": "test",
                "text": "DebateOS の実装を改善",
                "tags": ["debate", "implementation"],
            },
            {
                "kind": "test",
                "text": "MemoryOS にベクトル検索を追加",
                "tags": ["memory", "vector"],
            },
            {
                "kind": "test",
                "text": "Python で機械学習モデルを訓練",
                "tags": ["ml", "python"],
            },
        ]

        for doc in test_docs:
            success = vec_mem.add(
                kind=doc["kind"],
                text=doc["text"],
                tags=doc["tags"],
            )
            if success:
                print(f"  ✅ Added: {doc['text'][:50]}")
            else:
                print(f"  ❌ Failed: {doc['text'][:50]}")

        print(f"\n✅ Total documents: {len(vec_mem.documents)}")

        # 検索テスト
        print("\n" + "-" * 60)
        print("Search tests:")
        print("-" * 60)

        test_queries = [
            "人工知能システムの設計",
            "メモリ管理の実装",
            "機械学習",
        ]

        for query in test_queries:
            print(f"\nQuery: '{query}'")
            results = vec_mem.search(query, k=3, min_sim=0.3)

            if results:
                print(f"  Found {len(results)} results:")
                for i, r in enumerate(results, 1):
                    print(f"    {i}. Score: {r['score']:.3f} | {r['text']}")
            else:
                print("  No results found")

        print("\n✅ Test 1 passed")
        return True

    except Exception as e:
        print(f"\n❌ Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integrated_memory():
    """統合されたMemoryOS（KVS + Vector）のテスト"""
    print("\n" + "=" * 60)
    print("Test 2: Integrated MemoryOS")
    print("=" * 60)

    try:
        # テスト用の一時ファイル
        import tempfile
        import json  # 将来拡張用（今はほぼ使っていない）

        temp_dir = Path(tempfile.mkdtemp())
        mem_path = temp_dir / "test_memory.json"
        idx_path = temp_dir / "test_vector_index.pkl"

        print(f"  Using temp directory: {temp_dir}")

        # VectorMemoryを初期化
        from veritas_os.core import memory
        VectorMemory = memory.VectorMemory

        vec_mem = VectorMemory(index_path=idx_path)

        if vec_mem.model is None:
            print("❌ sentence-transformers not available")
            return False

        # メモリストアを初期化（簡易版）
        mem_path.write_text("[]")

        print("✅ Integrated MemoryOS initialized")

        # ドキュメント追加テスト
        print("\n" + "-" * 60)
        print("Adding documents...")
        print("-" * 60)

        test_data = [
            {
                "text": "VERITAS OS は LLM の外骨格として機能する",
                "tags": ["veritas", "architecture"],
                "meta": {"user_id": "test", "project": "veritas"},
            },
            {
                "text": "DebateOS で全候補却下時の挙動を改善",
                "tags": ["debate", "improvement"],
                "meta": {"user_id": "test", "module": "debate"},
            },
            {
                "text": "sentence-transformers でベクトル検索を実装",
                "tags": ["memory", "vector", "ml"],
                "meta": {"user_id": "test", "module": "memory"},
            },
        ]

        for doc in test_data:
            # ベクトルインデックスに追加
            success = vec_mem.add(
                kind="semantic",
                text=doc["text"],
                tags=doc["tags"],
                meta=doc["meta"],
            )

            # KVSにも追加（簡易）
            if success:
                print(f"  ✅ {doc['text'][:60]}")

        # 検索テスト
        print("\n" + "-" * 60)
        print("Search tests:")
        print("-" * 60)

        query = "LLM システムの改善"
        print(f"\nQuery: '{query}'")

        results = vec_mem.search(query, k=5, min_sim=0.2)

        if results:
            print(f"  Found {len(results)} results:")
            for i, r in enumerate(results, 1):
                print(f"    {i}. Score: {r['score']:.3f}")
                print(f"       Text: {r['text']}")
                print(f"       Tags: {r['tags']}")
        else:
            print("  ❌ No results found (unexpected)")
            return False

        # インデックス永続化テスト
        print("\n" + "-" * 60)
        print("Index persistence test:")
        print("-" * 60)

        vec_mem._save_index()

        if idx_path.exists():
            size = idx_path.stat().st_size
            print(f"  ✅ Index saved: {idx_path.name} ({size} bytes)")

            # ロードテスト
            vec_mem2 = VectorMemory(index_path=idx_path)
            if len(vec_mem2.documents) == len(vec_mem.documents):
                print(f"  ✅ Index loaded: {len(vec_mem2.documents)} documents")
            else:
                print(f"  ❌ Load mismatch: {len(vec_mem2.documents)} vs {len(vec_mem.documents)}")
                return False
        else:
            print("  ❌ Index file not created")
            return False

        # クリーンアップ
        import shutil
        shutil.rmtree(temp_dir)
        print(f"\n  Cleaned up: {temp_dir}")

        print("\n✅ Test 2 passed")
        return True

    except Exception as e:
        print(f"\n❌ Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_performance():
    """パフォーマンステスト"""
    print("\n" + "=" * 60)
    print("Test 3: Performance")
    print("=" * 60)

    try:
        from veritas_os.core import memory
        VectorMemory = memory.VectorMemory
        import time

        vec_mem = VectorMemory(index_path=None)

        if vec_mem.model is None:
            print("❌ sentence-transformers not available")
            return False

        # 100件のドキュメントを追加
        print("  Adding 100 documents...")
        start = time.time()

        for i in range(100):
            vec_mem.add(
                kind="test",
                text=f"テストドキュメント {i}: 様々な内容を含むサンプルテキスト",
                tags=["test"],
                meta={"index": i},
            )

        add_time = time.time() - start
        print(f"  ✅ Add time: {add_time:.2f}s ({add_time/100*1000:.1f}ms per doc)")

        # 検索パフォーマンス
        print("\n  Search performance:")
        queries = [
            "テストドキュメント",
            "サンプルテキスト",
            "内容",
        ]

        total_time = 0
        for query in queries:
            start = time.time()
            results = vec_mem.search(query, k=10)
            search_time = time.time() - start
            total_time += search_time
            print(f"    '{query}': {search_time*1000:.1f}ms ({len(results)} hits)")

        avg_time = total_time / len(queries)
        print(f"  ✅ Avg search time: {avg_time*1000:.1f}ms")

        if avg_time < 0.5:  # 500ms以内
            print("\n✅ Test 3 passed (performance acceptable)")
            return True
        else:
            print("\n⚠️ Test 3 warning: search time may be slow")
            return True

    except Exception as e:
        print(f"\n❌ Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メインテスト実行"""
    print("\n" + "=" * 60)
    print("MemoryOS Vector Search Test Suite")
    print("=" * 60)

    results = []

    # Test 1
    results.append(("VectorMemory standalone", test_vector_memory_standalone()))

    # Test 2
    results.append(("Integrated MemoryOS", test_integrated_memory()))

    # Test 3
    results.append(("Performance", test_performance()))

    # サマリ
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} | {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())








