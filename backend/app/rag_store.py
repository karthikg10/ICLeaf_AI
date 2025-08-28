# backend/app/rag_store.py
from typing import List, Tuple, Dict, Any
import chromadb
from chromadb.config import Settings
from openai import OpenAI
import app.deps as deps

# --- Embeddings via OpenAI ---
_client = OpenAI(api_key=deps.OPENAI_API_KEY)

def _embed(texts: List[str]) -> List[List[float]]:
    """
    Return embedding vectors for a list of texts.
    """
    resp = _client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]

# --- Persistent ChromaDB ---
_chroma = chromadb.PersistentClient(
    path="./data/chroma",
    settings=Settings(is_persistent=True),
)
_collection = _chroma.get_or_create_collection(
    name="icleaf_docs",
    metadata={"hnsw:space": "cosine"},
)

def _sanitize_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            # drop or coerce; Chroma metadata must be Bool | Int | Float | Str
            continue
        if isinstance(v, (bool, int, float, str)):
            out[k] = v
        else:
            out[k] = str(v)
    return out

def add_documents(docs: List[Tuple[str, Dict[str, Any]]]) -> None:
    if not docs:
        return
    ids, texts, metas = [], [], []
    for i, (text, meta) in enumerate(docs):
        ids.append(str(meta.get("id") or f"doc_{i}"))
        texts.append(text)
        metas.append(_sanitize_meta(meta))
    embs = _embed(texts)
    _collection.add(ids=ids, documents=texts, metadatas=metas, embeddings=embs)


def query(q: str, top_k: int = 4):
    """
    Semantic search; returns list of dicts {text, meta, score}.
    """
    if not q.strip():
        return []
    q_emb = _embed([q])[0]
    res = _collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    items = []
    if res and res.get("documents"):
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        for doc, meta, dist in zip(docs, metas, dists):
            items.append({"text": doc, "meta": meta, "score": float(1.0 - dist)})
    return items


# backend/app/rag_store.py  (append these helpers)

def reset_index() -> None:
    """
    Drop and recreate the Chroma collection.
    """
    global _collection
    try:
        _chroma.delete_collection("icleaf_docs")
    except Exception:
        pass
    _collection = _chroma.get_or_create_collection(
        name="icleaf_docs",
        metadata={"hnsw:space": "cosine"},
    )

def count() -> int:
    try:
        return _collection.count()
    except Exception:
        return 0


def all_documents(limit: int = 100000):
    # returns documents + metadatas for analysis
    try:
        got = _collection.get(include=["documents", "metadatas"])
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        # flatten (Chroma returns lists-of-lists sometimes)
        if isinstance(docs, list) and docs and isinstance(docs[0], list):
            docs = docs[0]
            metas = metas[0]
        return docs, metas
    except Exception:
        return [], []
