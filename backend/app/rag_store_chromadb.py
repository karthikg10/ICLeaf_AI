# backend/app/rag_store_chromadb.py

import os
import uuid
from typing import List, Dict, Any, Optional
import logging
import chromadb

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChromaRAGStore:
    def __init__(self, persist_directory: str = "./data/chroma"):
        """Initialize ChromaDB RAG store with OpenAI embeddings."""
        self.persist_directory = persist_directory
        self.collection_name = "documents"
        
        try:
            # Initialize ChromaDB client with persistent storage
            self.client = chromadb.PersistentClient(path=persist_directory)
            logger.info(f"[RAG] Initialized ChromaDB at {persist_directory}")
            
            # Create collection WITHOUT embedding function
            # We'll provide embeddings explicitly using OpenAI
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "ICLeaF AI Document Collection"}
                # ← NO embedding_function parameter
                # We'll provide embeddings manually
            )
            
            logger.info(f"[RAG] Using collection '{self.collection_name}' with OpenAI embeddings (1536-dim)")
            
        except Exception as e:
            logger.error(f"[RAG] Error initializing ChromaDB: {e}")
            raise

    def add_documents(self, docs: List[tuple]) -> int:
        """
        Add documents to ChromaDB with OpenAI embeddings.
        
        Args:
            docs: List of (text, metadata) tuples
            
        Returns:
            Number of documents successfully added
        """
        if not docs:
            logger.warning("[RAG] No documents to add")
            return 0
        
        try:
            # Import embedding service
            from . import embedding_service
            
            texts = []
            embeddings = []
            metadatas = []
            ids = []
            failed_count = 0
            
            print(f"\n[RAG] Processing {len(docs)} chunks for OpenAI embeddings...")
            
            for i, (text, meta) in enumerate(docs):
                # Validate text
                if not text or not isinstance(text, str) or not text.strip():
                    logger.warning(f"[RAG] Skipping chunk {i+1}: empty or invalid text")
                    failed_count += 1
                    continue
                
                # Clean text
                clean_text = text.strip()
                clean_text = " ".join(clean_text.split())  # Normalize whitespace
                
                if len(clean_text) < 10:  # Skip very short chunks
                    logger.warning(f"[RAG] Skipping chunk {i+1}: too short ({len(clean_text)} chars)")
                    failed_count += 1
                    continue
                
                # Generate OpenAI embedding (1536 dimensions)
                print(f"[RAG] Generating embedding {i+1}/{len(docs)}...", end="\r")
                embedding = embedding_service.embed_text(clean_text)
                
                if not embedding:
                    logger.warning(f"[RAG] Failed to generate embedding for chunk {i+1}")
                    failed_count += 1
                    continue
                
                # Verify embedding dimension
                if len(embedding) != 1536:
                    logger.warning(f"[RAG] Wrong embedding dimension {len(embedding)} (expected 1536)")
                    failed_count += 1
                    continue
                
                # Add to lists
                texts.append(clean_text)
                embeddings.append(embedding)
                
                # Prepare metadata
                metadata = {
                    "filename": meta.get("filename", "unknown"),
                    "title": meta.get("title", meta.get("filename", "Document")),
                    "docName": meta.get("docName", meta.get("filename", "")),
                    "subjectId": meta.get("subjectId", ""),
                    "topicId": meta.get("topicId", ""),
                    "uploadedBy": meta.get("uploadedBy", ""),
                    "chunk_index": str(meta.get("chunk_index", i)),
                }
                # Add docId to metadata if present
                if "docId" in meta:
                    metadata["docId"] = meta["docId"]
                metadatas.append(metadata)
                
                # Generate unique ID
                ids.append(str(uuid.uuid4()))
            
            print("\n")  # New line after progress
            
            if not texts:
                logger.warning("[RAG] No valid chunks with embeddings to add")
                return 0
            
            print(f"[RAG] Adding {len(texts)} chunks with OpenAI embeddings to ChromaDB...")
            print(f"[RAG] Embeddings: {len(embeddings)} x 1536-dimensional")
            
            # ✅ Add documents with OpenAI embeddings
            self.collection.add(
                documents=texts,
                embeddings=embeddings,  # 1536-dim OpenAI embeddings
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"[RAG] Successfully added {len(texts)} documents with 1536-dim embeddings")
            
            if failed_count > 0:
                logger.warning(f"[RAG] Failed to process {failed_count} chunks")
            
            print(f"[RAG] ✓ Successfully stored {len(texts)} chunks with OpenAI embeddings (1536-dim)\n")
            
            return len(texts)
            
        except Exception as e:
            logger.error(f"[RAG] Error adding documents: {e}")
            raise


    def query(
        self,
        query_text: str,
        top_k: int = 5,
        min_similarity: float = 0.5,
        subject_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        doc_name: Optional[str] = None,
        doc_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query the RAG store using OpenAI embeddings."""
        if not query_text or not query_text.strip():
            logger.warning("[RAG] Empty query text")
            return []

        try:
            from . import embedding_service

            # 1) Make the query embedding
            query_embedding = embedding_service.embed_text(query_text)
            if not query_embedding:
                logger.error("[RAG] Failed to generate query embedding")
                return []

            # 2) Build a valid 'where' dict (AND semantics)
            where: Optional[Dict[str, Any]] = {}
            if subject_id:
                where["subjectId"] = subject_id
            if topic_id:
                where["topicId"] = topic_id
            if doc_name:
                where["docName"] = doc_name
            if doc_id:
                where["docId"] = doc_id
            if not where:
                where = None  # let Chroma ignore it

            # 3) Query Chroma
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            # 4) Flatten the first (and only) query's lists
            docs      = (results.get("documents") or [[]])[0]
            metas     = (results.get("metadatas") or [[]])[0]
            dists     = (results.get("distances") or [[]])[0]
            ids       = (results.get("ids") or [[]])[0]

            hits: List[Dict[str, Any]] = []
            for doc, meta, dist, _id in zip(docs, metas, dists, ids):
                if doc is None:
                    continue
                try:
                    distance = float(dist) if dist is not None else 1.0
                except (TypeError, ValueError):
                    continue

                # Chroma returns a distance (cosine by default). Convert to similarity.
                # Don't clamp to 0.0 - store actual similarity value (can be negative for very dissimilar vectors)
                # This ensures we always have a real score for validation
                similarity = 1.0 - distance
                if similarity >= min_similarity:
                    hits.append({
                        "id": _id,
                        "text": doc,
                        "score": round(similarity, 6),  # Store actual similarity, even if negative
                        "meta": meta or {},
                    })

            # Highest similarity first
            hits.sort(key=lambda x: x["score"], reverse=True)
            
            # Debug: Log score range for troubleshooting
            if hits:
                scores = [h["score"] for h in hits]
                logger.info(f"[RAG] Query: '{query_text[:50]}...' -> {len(hits)} results (min_sim={min_similarity}, score_range=[{min(scores):.3f}, {max(scores):.3f}])")
            else:
                logger.info(f"[RAG] Query: '{query_text[:50]}...' -> {len(hits)} results (min_sim={min_similarity})")
            
            return hits

        except Exception as e:
            logger.error(f"[RAG] Error querying: {e}")
            import traceback; traceback.print_exc()
            return []


    # def query(
    #     self,
    #     query_text: str,
    #     top_k: int = 5,
    #     min_similarity: float = 0.5,
    #     subject_id: Optional[str] = None,
    #     topic_id: Optional[str] = None,
    #     doc_name: Optional[str] = None,
    # ) -> List[Dict[str, Any]]:
    #     """
    #     Query the RAG store using OpenAI embeddings.
        
    #     Args:
    #         query_text: The query text
    #         top_k: Number of results to return
    #         min_similarity: Minimum similarity threshold (0.0 to 1.0)
    #         subject_id: Optional subject filter
    #         topic_id: Optional topic filter
    #         doc_name: Optional document name filter
            
    #     Returns:
    #         List of matching documents with scores
    #     """
    #     if not query_text or not query_text.strip():
    #         logger.warning("[RAG] Empty query text")
    #         return []
        
    #     try:
    #         from . import embedding_service
            
    #         # Generate embedding for query using OpenAI
    #         query_embedding = embedding_service.embed_text(query_text)
            
    #         if not query_embedding:
    #             logger.error("[RAG] Failed to generate query embedding")
    #             return []
            
    #         # Build where filter if needed
    #         where_filter = None
    #         if subject_id or topic_id or doc_name:
    #             where_conditions = []
    #             if subject_id:
    #                 where_conditions.append({"subjectId": subject_id})
    #             if topic_id:
    #                 where_conditions.append({"topicId": topic_id})
    #             if doc_name:
    #                 where_conditions.append({"docName": doc_name})
                
    #             # Build filter (AND all conditions)
    #             if where_conditions:
    #                 where_filter = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions
            
    #         # Query with OpenAI embedding
    #         results = self.collection.query(
    #             query_embeddings=[query_embedding],  # Use OpenAI embedding
    #             n_results=top_k,
    #             where=where_filter,
    #             include=["documents", "metadatas", "distances"]
    #         )
            
    #         # ✅ FIXED: Process results with correct indexing
    #         hits = []
    #         if results and results["documents"] and len(results["documents"]) > 0:
    #             for i, doc in enumerate(results["documents"]):  # ✅ Use  for first element
    #                 try:
    #                     # ✅ FIXED: Get distance with correct indexing
    #                     distance_raw = results["distances"][i] if results["distances"] else 0
                        
    #                     # Convert to float, handling nested list format
    #                     if isinstance(distance_raw, (list, tuple)):
    #                         distance = float(distance_raw) if distance_raw else 0.0
    #                     else:
    #                         distance = float(distance_raw)
                        
    #                     # ChromaDB returns distances (cosine distance)
    #                     # Convert to similarity score: similarity = 1 - distance
    #                     similarity_score = max(0.0, 1.0 - distance)
                        
    #                     if similarity_score >= min_similarity:
    #                         hits.append({
    #                             "text": doc,
    #                             "score": similarity_score,
    #                             "meta": results["metadatas"][i],
    #                         })
                    
    #                 except (TypeError, IndexError, ValueError) as e:
    #                     logger.warning(f"[RAG] Error processing result {i}: {e}")
    #                     continue
            
    #         logger.info(f"[RAG] Query: '{query_text[:50]}...' -> {len(hits)} results (min_sim={min_similarity})")
            
    #         return hits
            
    #     except Exception as e:
    #         logger.error(f"[RAG] Error querying: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return []

    # def query(
    #     self,
    #     query_text: str,
    #     top_k: int = 5,
    #     min_similarity: float = 0.1,
    #     subject_id: Optional[str] = None,
    #     topic_id: Optional[str] = None,
    #     doc_name: Optional[str] = None,
    # ) -> List[Dict[str, Any]]:
    #     """
    #     Query the RAG store using OpenAI embeddings.
        
    #     Args:
    #         query_text: The query text
    #         top_k: Number of results to return
    #         min_similarity: Minimum similarity threshold (0.0 to 1.0)
    #         subject_id: Optional subject filter
    #         topic_id: Optional topic filter
    #         doc_name: Optional document name filter
            
    #     Returns:
    #         List of matching documents with scores
    #     """
    #     if not query_text or not query_text.strip():
    #         logger.warning("[RAG] Empty query text")
    #         return []
        
    #     try:
    #         from . import embedding_service
            
    #         # Generate embedding for query using OpenAI
    #         query_embedding = embedding_service.embed_text(query_text)
            
    #         if not query_embedding:
    #             logger.error("[RAG] Failed to generate query embedding")
    #             return []
            
    #         # Build where filter if needed
    #         where_filter = None
    #         if subject_id or topic_id or doc_name:
    #             where_conditions = []
    #             if subject_id:
    #                 where_conditions.append({"subjectId": subject_id})
    #             if topic_id:
    #                 where_conditions.append({"topicId": topic_id})
    #             if doc_name:
    #                 where_conditions.append({"docName": doc_name})
                
    #             # Build filter (AND all conditions)
    #             if where_conditions:
    #                 where_filter = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions
            
    #         # Query with OpenAI embedding
    #         results = self.collection.query(
    #             query_embeddings=[query_embedding],  # Use OpenAI embedding
    #             n_results=top_k,
    #             where=where_filter,
    #             include=["documents", "metadatas", "distances"]
    #         )
            
    #         # Process results
    #         hits = []
    #         if results and results["documents"] and len(results["documents"]) > 0:
    #             for i, doc in enumerate(results["documents"]):
    #                 distance = results["distances"][i] if results["distances"] else 0
                    
    #                 # ChromaDB returns distances (cosine distance)
    #                 # Convert to similarity score: similarity = 1 - distance
    #                 similarity_score = 1 - distance
                    
    #                 if similarity_score >= min_similarity:
    #                     hits.append({
    #                         "text": doc,
    #                         "score": similarity_score,
    #                         "meta": results["metadatas"][i],
    #                     })
            
    #         logger.info(f"[RAG] Query: '{query_text[:50]}...' -> {len(hits)} results (min_sim={min_similarity})")
            
    #         return hits
            
    #     except Exception as e:
    #         logger.error(f"[RAG] Error querying: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            collection_data = self.collection.get(include=["documents", "embeddings", "metadatas"])
            
            embedding_info = "N/A"
            if collection_data.get("embeddings") and len(collection_data["embeddings"]) > 0:
                first_embedding = collection_data["embeddings"]
                if first_embedding:
                    embedding_info = f"{len(first_embedding)}-dimensional"
            
            return {
                "total_documents": len(collection_data["ids"]),
                "collection_name": self.collection_name,
                "embedding_model": f"OpenAI text-embedding-3-small ({embedding_info})",
            }
        except Exception as e:
            logger.error(f"[RAG] Error getting stats: {e}")
            return {}

    def list_all_documents(self) -> List[Dict[str, Any]]:
        """Get a list of all unique documents with their docIds and metadata."""
        try:
            # Get all documents from ChromaDB
            collection_data = self.collection.get(include=["metadatas"])
            metadatas = collection_data.get("metadatas", [])
            
            # Create a dictionary to store unique documents by docId
            documents_map: Dict[str, Dict[str, Any]] = {}
            
            for meta in metadatas:
                if not meta:
                    continue
                
                doc_id = meta.get("docId")
                if not doc_id:
                    continue  # Skip chunks without docId (older documents)
                
                # If we haven't seen this docId yet, create an entry
                if doc_id not in documents_map:
                    documents_map[doc_id] = {
                        "docId": doc_id,
                        "docName": meta.get("docName", meta.get("filename", "Unknown")),
                        "filename": meta.get("filename", "Unknown"),
                        "title": meta.get("title", meta.get("filename", "Document")),
                        "subjectId": meta.get("subjectId", ""),
                        "topicId": meta.get("topicId", ""),
                        "uploadedBy": meta.get("uploadedBy", ""),
                        "chunkCount": 0  # Will count chunks below
                    }
                
                # Increment chunk count for this document
                documents_map[doc_id]["chunkCount"] = documents_map[doc_id].get("chunkCount", 0) + 1
            
            # Convert to list
            documents = list(documents_map.values())
            
            # Sort by docName for better UX
            documents.sort(key=lambda x: x.get("docName", "").lower())
            
            logger.info(f"[RAG] Listed {len(documents)} unique documents")
            return documents
            
        except Exception as e:
            logger.error(f"[RAG] Error listing documents: {e}")
            import traceback
            traceback.print_exc()
            return []


# Global instance
_rag_store: Optional[ChromaRAGStore] = None


def get_rag_store() -> ChromaRAGStore:
    """Get or create the global RAG store instance."""
    global _rag_store
    if _rag_store is None:
        _rag_store = ChromaRAGStore()
    return _rag_store


def add_documents(docs: List[tuple]) -> int:
    """Add documents to the RAG store."""
    store = get_rag_store()
    return store.add_documents(docs)


def query(
    query_text: str,
    top_k: int = 5,
    min_similarity: float = 0.1,
    subject_id: Optional[str] = None,
    topic_id: Optional[str] = None,
    doc_name: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query the RAG store."""
    store = get_rag_store()
    return store.query(query_text, top_k, min_similarity, subject_id, topic_id, doc_name, doc_id)


def count() -> int:
    """Get total document count in ChromaDB collection."""
    try:
        store = get_rag_store()
        collection_data = store.collection.get()
        return len(collection_data["ids"])
    except Exception as e:
        logger.error(f"[RAG] Error counting documents: {e}")
        return 0

def list_all_documents() -> List[Dict[str, Any]]:
    """List all unique documents with their docIds."""
    store = get_rag_store()
    return store.list_all_documents()

