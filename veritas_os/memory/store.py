from pathlib import Path
import json, time, uuid
from typing import Dict, Any, List, Optional
from .embedder import HashEmbedder
from .index_cosine import CosineIndex
from veritas_os.core.atomic_io import atomic_append_line

# プロジェクトルート基準に変更
BASE_DIR = Path(__file__).resolve().parents[2]      # veritas_clean_test2
VERITAS_DIR = BASE_DIR / "veritas_os"
HOME_MEMORY = VERITAS_DIR / "memory"               # ← プロジェクト内メモリ
HOME_MEMORY.mkdir(parents=True, exist_ok=True)

BASE = HOME_MEMORY

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
    def __init__(self, dim=384):
        self.emb = HashEmbedder(dim=dim)
        # ★ 各 kind ごとに index ファイルパスを渡す
        self.idx = {
            k: CosineIndex(dim, INDEX[k])
            for k in FILES.keys()
        }
        self._boot()

    def _boot(self):
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

            ids, texts = [], []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        j = json.loads(line)
                        ids.append(j["id"])
                        texts.append(
                            j.get("text")
                            or j.get("summary")
                            or j.get("snippet", "")
                        )
                    except Exception:
                        continue

            if texts:
                vecs = self.emb.embed(texts)
                idx.add(vecs, ids)  # ★ ここで追加すると .npz 保存まで自動で行われる

    def put(self, kind: str, item: Dict[str, Any]) -> str:
        assert kind in FILES
        j = {
            "id":   item.get("id") or uuid.uuid4().hex,
            "ts":   item.get("ts") or time.time(),
            "tags": item.get("tags") or [],
            "text": item.get("text") or "",
            "meta": item.get("meta") or {},
        }
        # JSONL へ追記（atomic append with fsync）
        atomic_append_line(FILES[kind], json.dumps(j, ensure_ascii=False))

        # index へ追加（.npz も自動で更新）
        self.idx[kind].add(self.emb.embed([j["text"]]), [j["id"]])
        return j["id"]

    def search(
        self,
        query: str,
        k: int = 8,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.25,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:

        # topk → k 互換
        if "topk" in kwargs and kwargs["topk"] is not None:
            try:
                k = int(kwargs.pop("topk"))
            except:
                pass

        query = (query or "").strip()
        if not query:
            return {}

        kinds = kinds or list(FILES.keys())

        qv = self.emb.embed([query])

        out: Dict[str, List[Dict[str, Any]]] = {}

        for kind in kinds:
            try:
                raw = self.idx[kind].search(qv, k=k)
            except Exception as e:
                print(f"[MemoryStore] index search error for {kind}:", e)
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
                except Exception:
                    continue
                try:
                    pairs.append((_id, float(sc)))
                except:
                    pairs.append((_id, 0.0))

            # JSONL 読み込み
            items = []
            try:
                with open(FILES[kind], encoding="utf-8") as f:
                    for line in f:
                        try:
                            items.append(json.loads(line))
                        except:
                            pass
            except:
                pass

            table = {it["id"]: it for it in items}

            hits: List[Dict[str, Any]] = []
            for _id, score in pairs:
                if float(score) < float(min_sim):
                    continue
                it = table.get(_id)
                if not it:
                    continue
                hits.append({**it, "score": float(score)})

            hits.sort(key=lambda h: h.get("score", 0.0), reverse=True)
            out[kind] = hits[:k]

        return out

    def put_episode(self, text, tags=None, meta=None):
        item = {
            "text": text,
            "tags": tags or ["episode"],
            "meta": meta or {},
            "ts": time.time(),
            }
        return self.put("episodic", item)
