# backend/app/rag_store_chromadb.py
# ChromaDB-based RAG store for production use with fallback to simple store

import os
import uuid
from typing import List, Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import ChromaDB, fallback to simple store if it fails
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ChromaDB not available: {e}, falling back to simple RAG store")
    CHROMADB_AVAILABLE = False

# Note: Simple RAG store fallback removed - ChromaDB only

class ChromaRAGStore:
    def __init__(self, persist_directory: str = "./data/chroma"):
        """Initialize ChromaDB RAG store with persistent storage."""
        self.persist_directory = persist_directory
        self.collection_name = "documents"
        self.use_fallback = False
        
        if not CHROMADB_AVAILABLE:
            logger.error("ChromaDB not available and no fallback configured")
            raise ImportError("ChromaDB is required but not available")
        
        # Ensure directory exists
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB client with error handling
        try:
            self.client = chromadb.PersistentClient(path=persist_directory)
            logger.info("ChromaDB persistent client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to create ChromaDB client: {e}")
            raise RuntimeError(f"Failed to initialize ChromaDB: {e}")
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            logger.info(f"Connected to existing collection: {self.collection_name}")
        except Exception:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "ICLeaF AI Document Collection"}
            )
            logger.info(f"Created new collection: {self.collection_name}")
    
    def reset_index(self):
        """Reset the document index by deleting and recreating the collection."""
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "ICLeaF AI Document Collection"}
            )
            logger.info("[RAG] Index reset successfully")
        except Exception as e:
            logger.error(f"Error resetting index: {e}")
    
    def add_documents(self, docs: List[tuple]):
        """Add documents to the ChromaDB collection."""
        if not docs:
            return
        
        texts = []
        metadatas = []
        ids = []
        
        for text, meta in docs:
            # Generate unique ID for each document
            doc_id = str(uuid.uuid4())
            
            # Prepare text and metadata
            texts.append(text)
            metadatas.append({
                "filename": meta.get("filename", "unknown"),
                "title": meta.get("title", meta.get("filename", "Document")),
                "subjectId": meta.get("subjectId", ""),
                "topicId": meta.get("topicId", ""),
                "docName": meta.get("docName", ""),
                "uploadedBy": meta.get("uploadedBy", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "source": meta.get("source", "upload")
            })
            ids.append(doc_id)
        
        try:
            # Add documents to collection
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"[RAG] Added {len(docs)} documents to ChromaDB")
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            raise
    
    def query(self, query_text: str, top_k: int = 5, min_similarity: float = 0.7, 
              subject_id: Optional[str] = None, topic_id: Optional[str] = None, 
              doc_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query the ChromaDB collection with similarity scoring and filtering.
        
        Args:
            query_text: The query string
            top_k: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            subject_id: Filter by subject ID
            topic_id: Filter by topic ID
            doc_name: Filter by document name
        
        Returns:
            List of documents with similarity scores >= min_similarity
        """
        try:
            # Build where clause for metadata filtering
            where_clause = {}
            if subject_id:
                where_clause["subjectId"] = subject_id
            if topic_id:
                where_clause["topicId"] = topic_id
            if doc_name:
                where_clause["docName"] = doc_name
            
            # Query the collection
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(top_k, 20),  # Query more than needed to filter by similarity
                where=where_clause if where_clause else None,
                include=["documents", "metadatas", "distances"]
            )
            
            # Process results
            documents = results["documents"][0] if results["documents"] else []
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []
            
            # Convert distances to similarity scores (ChromaDB uses cosine distance)
            # Cosine similarity = 1 - cosine distance
            similarity_scores = [1.0 - dist for dist in distances]
            
            # Filter by minimum similarity and create results
            filtered_results = []
            for i, (doc, meta, similarity) in enumerate(zip(documents, metadatas, similarity_scores)):
                if similarity >= min_similarity:
                    filtered_results.append({
                        "text": doc,
                        "meta": meta,
                        "score": float(similarity),
                        "id": results["ids"][0][i] if results["ids"] else f"doc_{i}"
                    })
            
            # Sort by similarity score (descending) and limit to top_k
            filtered_results.sort(key=lambda x: x["score"], reverse=True)
            filtered_results = filtered_results[:top_k]
            
            logger.info(f"[RAG] Query: '{query_text[:50]}...' -> {len(filtered_results)} results (min_sim={min_similarity})")
            return filtered_results
            
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            return []
    
    def count(self) -> int:
        """Get document count."""
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Error getting document count: {e}")
            return 0
    
    def all_documents(self):
        """Get all documents (for migration purposes)."""
        try:
            results = self.collection.get(include=["documents", "metadatas"])
            texts = results["documents"] if results["documents"] else []
            metas = results["metadatas"] if results["metadatas"] else []
            return texts, metas
        except Exception as e:
            logger.error(f"Error getting all documents: {e}")
            return [], []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection information."""
        try:
            count = self.collection.count()
            return {
                "name": self.collection_name,
                "count": count,
                "persist_directory": self.persist_directory,
                "type": "chromadb"
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {"name": self.collection_name, "count": 0, "persist_directory": self.persist_directory, "type": "error"}

# Global instance
_rag_store = None

def get_rag_store() -> ChromaRAGStore:
    """Get the global RAG store instance."""
    global _rag_store
    if _rag_store is None:
        _rag_store = ChromaRAGStore()
    return _rag_store

# Convenience functions for backward compatibility
def reset_index():
    """Reset the document index."""
    get_rag_store().reset_index()

def add_documents(docs: List[tuple]):
    """Add documents to the index."""
    get_rag_store().add_documents(docs)

def query(query_text: str, top_k: int = 5, min_similarity: float = 0.7, 
          subject_id: Optional[str] = None, topic_id: Optional[str] = None, 
          doc_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query documents with similarity scoring."""
    return get_rag_store().query(query_text, top_k, min_similarity, subject_id, topic_id, doc_name)

def count() -> int:
    """Get document count."""
    return get_rag_store().count()

def all_documents():
    """Get all documents."""
    return get_rag_store().all_documents()

def get_collection_info() -> Dict[str, Any]:
    """Get collection information."""
    return get_rag_store().get_collection_info()
