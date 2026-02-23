from pathlib import Path
import json
import logging
import math
import os
import threading
import time
import uuid
from typing import Dict, Any, List, Optional
from .embedder import HashEmbedder
from .index_cosine import CosineIndex
from veritas_os.core.atomic_io import atomic_append_line

logger = logging.getLogger(__name__)

# ★ M-3 修正: メモリディレクトリを環境変数で設定可能にする
# VERITAS_MEMORY_DIR が設定されていればそちらを使用、未設定ならプロジェクト内のデフォルト
_env_memory_dir = os.getenv("VERITAS_MEMORY_DIR", "").strip()
if _env_memory_dir:
    HOME_MEMORY = Path(_env_memory_dir)
else:
    BASE_DIR = Path(__file__).resolve().parents[2]      # veritas_clean_test2
    VERITAS_DIR = BASE_DIR / "veritas_os"
    HOME_MEMORY = VERITAS_DIR / "memory"               # ← プロジェクト内メモリ
HOME_MEMORY.mkdir(parents=True, exist_ok=True)

BASE = HOME_MEMORY

# クエリ長の上限（DoS対策）
MAX_QUERY_LENGTH = 10000

# 登録テキスト長の上限（DoS/ストレージ膨張対策）
MAX_ITEM_TEXT_LENGTH = 20000

# ID 長の上限（ログ肥大化・メモリ枯渇対策）
MAX_ITEM_ID_LENGTH = 128

# タグ数・タグ長の上限（メタデータ過剰入力による DoS/ログ肥大化対策）
MAX_TAGS_PER_ITEM = 64
MAX_TAG_LENGTH = 128

# JSONL ファイルサイズの上限（起動時の再構築 / 検索時の読み込み用、100MB）
MAX_JSONL_FILE_SIZE = 100 * 1024 * 1024

# ★ OOM対策: 検索時にメモリに読み込む最大アイテム数
MAX_SEARCH_ITEMS = 500_000

FILES = {
    "episodic": BASE / "episodic.jsonl",
    "semantic": BASE / "semantic.jsonl",
    "skills":   BASE / "skills.jsonl",
}

INDEX = {
    "episodic": BASE / "episodic.index.npz",
    "semantic": BASE / "semantic.index.npz",
    "skills":   BASE / "skills.index.npz",
}


class MemoryStore:
    """
    メモリストア（エピソード記憶・意味記憶・スキル）

    スレッドセーフ: 全ての読み書き操作は RLock で保護されています。
    FastAPI の並行リクエストでも安全に使用できます。
    """

    def __init__(self, dim: int = 384) -> None:
        self._lock = threading.RLock()  # リエントラントロック
        self.emb = HashEmbedder(dim=dim)
        # 段階キャッシュ（kind -> id -> payload）
        self._payload_cache: Dict[str, Dict[str, Dict[str, Any]]] = {
            kind: {} for kind in FILES
        }
        # True のときは「その kind の JSONL 全件がキャッシュ済み」を示す
        self._cache_complete: Dict[str, bool] = {kind: False for kind in FILES}
        # ★ 各 kind ごとに index ファイルパスを渡す
        self.idx = {
            k: CosineIndex(dim, INDEX[k])
            for k in FILES.keys()
        }
        self._boot()

    def _boot(self) -> None:
        """
        - 既に index（.npz）があればそれを使う
        - index が空で jsonl が存在する場合だけ、jsonl から再構築
        """
        for kind, path in FILES.items():
            idx = self.idx[kind]

            # もうデータがある（.npzロード済み）ならスキップ
            if getattr(idx, "size", 0) > 0:
                continue

            if not path.exists():
                continue

            # OOM防止: 大きすぎるファイルは再構築をスキップ
            try:
                file_size = path.stat().st_size
                if file_size > MAX_JSONL_FILE_SIZE:
                    logger.warning("[MemoryStore] %s too large for boot rebuild (%d bytes), skipping",
                                   kind, file_size)
                    continue
            except OSError:
                continue

            ids, texts = [], []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        j = json.loads(line)
                        ids.append(j["id"])
                        self._payload_cache[kind][j["id"]] = j
                        texts.append(
                            j.get("text")
                            or j.get("summary")
                            or j.get("snippet", "")
                        )
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # 不正なJSONまたは必須フィールド欠損をスキップ
                        continue
                    # ★ OOM対策: ブート時の再構築もアイテム数上限を適用
                    if len(ids) >= MAX_SEARCH_ITEMS:
                        logger.warning(
                            "[MemoryStore] %s hit MAX_SEARCH_ITEMS (%d) during boot, truncating",
                            kind, MAX_SEARCH_ITEMS,
                        )
                        break

            self._cache_complete[kind] = len(ids) < MAX_SEARCH_ITEMS

            if texts:
                vecs = self.emb.embed(texts)
                idx.add(vecs, ids)  # ★ ここで追加すると .npz 保存まで自動で行われる
            else:
                logger.warning("[MemoryStore] No valid items found in %s for kind=%s", path, kind)

    def put(self, kind: str, item: Dict[str, Any]) -> str:
        """
        メモリにアイテムを追加（スレッドセーフ）

        Args:
            kind: "episodic", "semantic", or "skills"
            item: 追加するアイテム（id, ts, tags, text, meta）

        Returns:
            追加されたアイテムのID
        """
        if kind not in FILES:
            raise ValueError(f"Unknown memory kind: {kind!r}. Must be one of {set(FILES)}")

        j = self._normalize_item(item)

        # ベクトル化（ロック外で実行 - 計算コストが高い）
        vec = self.emb.embed([j["text"]])

        with self._lock:
            # JSONL へ追記（atomic append with fsync）
            atomic_append_line(FILES[kind], json.dumps(j, ensure_ascii=False))

            # payload KV キャッシュ更新
            self._payload_cache[kind][j["id"]] = j

            # index へ追加（.npz も自動で更新）
            self.idx[kind].add(vec, [j["id"]])

        return j["id"]

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate a memory item before persistence.

        Security hardening:
        - `id` is normalized to a bounded, hashable string to avoid malformed
          payloads that can corrupt in-memory cache updates.
        - `text` length is bounded to reduce abuse risk.
        """
        if not isinstance(item, dict):
            raise TypeError("item must be a dict")

        item_id = item.get("id")
        if item_id is None:
            normalized_id = uuid.uuid4().hex
        else:
            if isinstance(item_id, (dict, list, set, tuple)):
                raise TypeError("item.id must be a scalar value")
            normalized_id = str(item_id).strip()
            if not normalized_id:
                raise ValueError("item.id must not be empty")
            if len(normalized_id) > MAX_ITEM_ID_LENGTH:
                raise ValueError(
                    f"item.id too long (max {MAX_ITEM_ID_LENGTH} chars)"
                )

        text = str(item.get("text") or "")
        if len(text) > MAX_ITEM_TEXT_LENGTH:
            raise ValueError(f"Item text too long (max {MAX_ITEM_TEXT_LENGTH} chars)")

        tags = item.get("tags") or []
        if not isinstance(tags, list):
            raise TypeError("item.tags must be a list")
        if len(tags) > MAX_TAGS_PER_ITEM:
            raise ValueError(
                f"item.tags too many (max {MAX_TAGS_PER_ITEM} items)"
            )

        normalized_tags: List[str] = []
        for raw_tag in tags:
            normalized_tag = str(raw_tag).strip()
            if not normalized_tag:
                raise ValueError("item.tags must not contain empty values")
            if len(normalized_tag) > MAX_TAG_LENGTH:
                raise ValueError(
                    f"item.tags element too long (max {MAX_TAG_LENGTH} chars)"
                )
            normalized_tags.append(normalized_tag)

        meta = item.get("meta") or {}
        if not isinstance(meta, dict):
            raise TypeError("item.meta must be a dict")

        return {
            "id": normalized_id,
            "ts": item.get("ts") or time.time(),
            "tags": normalized_tags,
            "text": text,
            "meta": meta,
        }

    def _load_payloads_for_ids(self, kind: str, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """JSONL を逐次走査し、指定 id の payload だけを読み込む。"""
        found: Dict[str, Dict[str, Any]] = {}
        if not ids:
            return found

        wanted = set(ids)
        path = FILES[kind]

        try:
            file_size = path.stat().st_size
            if file_size > MAX_JSONL_FILE_SIZE:
                logger.warning("[MemoryStore] %s too large for targeted payload load (%d bytes)",
                               kind, file_size)
                return found
        except OSError:
            return found

        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    _id = item.get("id")
                    if _id in wanted:
                        found[_id] = item
                        if len(found) >= len(wanted):
                            break
        except (OSError, IOError) as e:
            logger.warning("[MemoryStore] Failed targeted payload load from %s: %s", path, e)

        return found

    def search(
        self,
        query: str,
        k: int = 8,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.25,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        クエリに類似するメモリを検索（スレッドセーフ）

        Args:
            query: 検索クエリ文字列
            k: 取得する上位件数
            kinds: 検索対象の種類（デフォルトは全て）
            min_sim: 最小類似度閾値

        Returns:
            kind ごとの検索結果リスト
        """
        # topk → k 互換
        if "topk" in kwargs and kwargs["topk"] is not None:
            try:
                k = int(kwargs.pop("topk"))
            except (ValueError, TypeError):
                pass

        min_sim = self._normalize_min_sim(min_sim)

        query = (query or "").strip()
        if not query:
            return {}

        # ★ DoS対策: クエリ長の制限
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(f"Query too long (max {MAX_QUERY_LENGTH} chars)")

        # ★ DoS対策: k の上限を制限（メモリ枯渇防止）
        try:
            k = max(1, min(int(k), 1000))
        except (ValueError, TypeError):
            k = 8

        kinds = kinds or list(FILES.keys())

        # ベクトル化（ロック外で実行 - 計算コストが高い）
        qv = self.emb.embed([query])

        out: Dict[str, List[Dict[str, Any]]] = {}

        for kind in kinds:
            if kind not in FILES:
                logger.warning("[MemoryStore] Unknown kind in search: %s", kind)
                out[kind] = []
                continue

            with self._lock:
                # インデックス検索のみロック内で実行
                try:
                    raw = self.idx[kind].search(qv, k=k)
                except Exception as e:
                    logger.warning("[MemoryStore] index search error for %s: %s", kind, e)
                    out[kind] = []
                    continue

                # ★★★ NEW：CosineIndex.search() は [[(id,score),...]] なので flatten する
                # raw が空なら []
                if not raw:
                    out[kind] = []
                    continue

                # raw[0] が [(id,score),...]
                res = raw[0]

                # 正規化済みなのでそのまま pairs にする
                pairs = []
                for item in res:
                    try:
                        _id, sc = item
                    except (ValueError, TypeError):
                        # タプルアンパック失敗をスキップ
                        continue
                    try:
                        pairs.append((_id, float(sc)))
                    except (ValueError, TypeError):
                        pairs.append((_id, 0.0))

                candidate_ids = [item_id for item_id, _ in pairs]
                table = {
                    item_id: self._payload_cache[kind].get(item_id)
                    for item_id in candidate_ids
                }
                cache_complete = self._cache_complete.get(kind, False)

            # ロック外: miss 分のみ targeted load（段階キャッシュ）
            missing_ids = [item_id for item_id, payload in table.items() if payload is None]
            if missing_ids and not cache_complete:
                loaded = self._load_payloads_for_ids(kind, missing_ids)
                if loaded:
                    with self._lock:
                        self._payload_cache[kind].update(loaded)
                        for item_id, payload in loaded.items():
                            table[item_id] = payload

            hits: List[Dict[str, Any]] = []
            for _id, score in pairs:
                if float(score) < min_sim:
                    continue
                it = table.get(_id)
                if not it:
                    continue
                hits.append({**it, "score": float(score)})

            hits.sort(key=lambda h: h.get("score", 0.0), reverse=True)
            out[kind] = hits[:k]

        return out

    def put_episode(self, text: str, tags: Optional[List[str]] = None, meta: Optional[Dict[str, Any]] = None) -> str:
        item = {
            "text": text,
            "tags": tags or ["episode"],
            "meta": meta or {},
            "ts": time.time(),
            }
        return self.put("episodic", item)

    @staticmethod
    def _normalize_min_sim(value: Any) -> float:
        """Clamp min_sim to a finite [0.0, 1.0] value with a safe default."""
        default = 0.25
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return max(0.0, min(parsed, 1.0))
