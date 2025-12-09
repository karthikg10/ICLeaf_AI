#!/usr/bin/env python3
"""
Script to re-process a document with OCR enabled.
This is useful when a document was processed before OCR was properly configured,
or when OCR didn't run due to threshold conditions.

Usage:
    python reprocess_document.py <docId> [file_path]
    
If file_path is not provided, the script will try to find the document in ChromaDB metadata.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

import app.rag_store_chromadb as rag_store_chromadb
import app.embedding_service as embedding_service
from app.ingest_dir import _read_file_build_docs
import chromadb

def find_document_file(doc_id: str) -> str:
    """Find the file path for a document by docId."""
    try:
        # Import rag instance
        from app.rag_store_chromadb import get_rag_store
        store = get_rag_store()
        collection = store.collection
        
        # Get all documents with this docId
        results = collection.get(
            where={"docId": doc_id},
            limit=1
        )
        
        if results and results.get("metadatas") and len(results["metadatas"]) > 0:
            meta = results["metadatas"][0]
            filename = meta.get("filename", "")
            doc_name = meta.get("docName", "")
            
            # Try to find the file in common upload directories
            upload_dirs = [
                "./data/uploads",
                "./data/content",
                "../data/uploads",
                "../data/content"
            ]
            
            for upload_dir in upload_dirs:
                if os.path.exists(upload_dir):
                    for root, dirs, files in os.walk(upload_dir):
                        for file in files:
                            if file == filename or (doc_name and doc_name in file):
                                return os.path.join(root, file)
            
            print(f"[INFO] Found metadata: filename={filename}, docName={doc_name}")
            print(f"[INFO] Please provide the file path manually")
            return None
        else:
            print(f"[ERROR] Could not find document with docId: {doc_id}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Error finding document: {e}")
        return None

def delete_document_chunks(doc_id: str):
    """Delete all chunks for a document by docId."""
    try:
        from app.rag_store_chromadb import get_rag_store
        store = get_rag_store()
        collection = store.collection
        
        # Get all IDs for this docId
        results = collection.get(
            where={"docId": doc_id}
        )
        
        if results and results.get("ids"):
            ids_to_delete = results["ids"]
            print(f"[INFO] Found {len(ids_to_delete)} chunks to delete for docId: {doc_id}")
            
            # Delete chunks
            collection.delete(ids=ids_to_delete)
            print(f"[INFO] Deleted {len(ids_to_delete)} chunks")
            return len(ids_to_delete)
        else:
            print(f"[WARNING] No chunks found for docId: {doc_id}")
            return 0
            
    except Exception as e:
        print(f"[ERROR] Error deleting chunks: {e}")
        return 0

def reprocess_document(doc_id: str, file_path: str = None):
    """Re-process a document with OCR enabled."""
    print(f"[INFO] Re-processing document: {doc_id}")
    
    # Find file path if not provided
    if not file_path:
        print("[INFO] Searching for document file...")
        file_path = find_document_file(doc_id)
        if not file_path:
            print("[ERROR] Could not find document file. Please provide file_path.")
            return False
    
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return False
    
    print(f"[INFO] Found file: {file_path}")
    
    # Get metadata from existing chunks
    try:
        from app.rag_store_chromadb import get_rag_store
        store = get_rag_store()
        collection = store.collection
        
        results = collection.get(
            where={"docId": doc_id},
            limit=1
        )
        
        if not results or not results.get("metadatas") or len(results["metadatas"]) == 0:
            print("[ERROR] Could not find document metadata")
            return False
        
        meta = results["metadatas"][0]
        subject_id = meta.get("subjectId", "")
        topic_id = meta.get("topicId", "")
        doc_name = meta.get("docName", meta.get("filename", os.path.basename(file_path)))
        uploaded_by = meta.get("uploadedBy", "")
        
        print(f"[INFO] Document metadata:")
        print(f"  - docName: {doc_name}")
        print(f"  - subjectId: {subject_id}")
        print(f"  - topicId: {topic_id}")
        print(f"  - uploadedBy: {uploaded_by}")
        
    except Exception as e:
        print(f"[ERROR] Error getting metadata: {e}")
        return False
    
    # Delete old chunks
    print("[INFO] Deleting old chunks...")
    deleted_count = delete_document_chunks(doc_id)
    
    # Re-process document with OCR
    print("[INFO] Re-processing document with OCR enabled...")
    result = embedding_service.embed_single_file(
        file_path,
        subject_id,
        topic_id,
        doc_name,
        uploaded_by
    )
    
    if result.ok:
        print(f"[SUCCESS] Re-processed document successfully!")
        print(f"  - Chunks processed: {result.chunks_processed}")
        print(f"  - New docId: {result.docId}")
        return True
    else:
        print(f"[ERROR] Failed to re-process document: {result.message}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reprocess_document.py <docId> [file_path]")
        sys.exit(1)
    
    doc_id = sys.argv[1]
    file_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = reprocess_document(doc_id, file_path)
    sys.exit(0 if success else 1)

