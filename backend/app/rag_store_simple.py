# backend/app/rag_store_simple.py
# Simplified RAG store for testing without ChromaDB dependencies

from typing import List, Dict, Any
import os

# Simple in-memory storage for testing
_documents: List[Dict[str, Any]] = []
_collection_name = "documents"

def reset_index():
    """Reset the document index."""
    global _documents
    _documents = []
    print("[RAG] Index reset")

def add_documents(docs: List[tuple]):
    """Add documents to the index."""
    global _documents
    for text, meta in docs:
        _documents.append({
            "text": text,
            "meta": meta,
            "id": meta.get("id", f"doc_{len(_documents)}")
        })
    print(f"[RAG] Added {len(docs)} documents")

def query(query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Simple query implementation."""
    # For testing, return mock results
    results = []
    for i, doc in enumerate(_documents[:top_k]):
        results.append({
            "text": doc["text"][:200] + "...",  # Truncate for display
            "meta": doc["meta"],
            "score": 0.9 - (i * 0.1)  # Mock relevance scores
        })
    return results

def count() -> int:
    """Get document count."""
    return len(_documents)

def all_documents():
    """Get all documents."""
    texts = [doc["text"] for doc in _documents]
    metas = [doc["meta"] for doc in _documents]
    return texts, metas
