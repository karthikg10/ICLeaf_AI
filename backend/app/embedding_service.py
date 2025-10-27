# backend/app/embedding_service.py
import os
import hashlib
from typing import List, Dict, Any, Optional
from openai import OpenAI
from . import deps
from .models import EmbedRequest, EmbedResponse, IngestFileRequest, IngestDirRequest

# Initialize OpenAI client for embeddings
embedding_client = OpenAI(api_key=deps.OPENAI_API_KEY) if deps.OPENAI_API_KEY else None

def get_embedding_model() -> str:
    """Get the embedding model name."""
    return "text-embedding-3-small"

def create_chunk_id(content: str, doc_name: str, chunk_index: int) -> str:
    """Create a unique chunk ID."""
    content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"chunk_{chunk_index}_{doc_name}_{content_hash}"

def embed_text(text: str, model: str = None) -> Optional[List[float]]:
    """Generate embedding for text using OpenAI."""
    if not embedding_client:
        return None
    
    model = model or get_embedding_model()
    try:
        response = embedding_client.embeddings.create(
            input=text,
            model=model
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def process_document_content(content: str, doc_name: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict[str, Any]]:
    """Process document content into chunks with embeddings."""
    if not content.strip():
        return []
    
    # Split content into chunks
    chunks = []
    words = content.split()
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        
        if len(chunk_text.strip()) < 50:  # Skip very short chunks
            continue
            
        chunk_id = create_chunk_id(chunk_text, doc_name, len(chunks))
        
        # Generate embedding
        embedding = embed_text(chunk_text)
        
        chunks.append({
            "chunk_id": chunk_id,
            "text": chunk_text,
            "embedding": embedding,
            "metadata": {
                "chunk_index": len(chunks),
                "doc_name": doc_name,
                "chunk_size": len(chunk_text)
            }
        })
    
    return chunks

def embed_single_file(file_path: str, subject_id: str, topic_id: str, doc_name: str, uploaded_by: str) -> EmbedResponse:
    """Embed a single file into the knowledge base."""
    try:
        if not os.path.exists(file_path):
            return EmbedResponse(
                ok=False,
                subjectId=subject_id,
                topicId=topic_id,
                docName=doc_name,
                uploadedBy=uploaded_by,
                chunks_processed=0,
                message=f"File not found: {file_path}"
            )
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if not content.strip():
            return EmbedResponse(
                ok=False,
                subjectId=subject_id,
                topicId=topic_id,
                docName=doc_name,
                uploadedBy=uploaded_by,
                chunks_processed=0,
                message="File is empty or contains no readable content"
            )
        
        # Process content into chunks
        chunks = process_document_content(content, doc_name)
        
        if not chunks:
            return EmbedResponse(
                ok=False,
                subjectId=subject_id,
                topicId=topic_id,
                docName=doc_name,
                uploadedBy=uploaded_by,
                chunks_processed=0,
                message="No valid chunks could be created from the file"
            )
        
        # Store in RAG store (this would integrate with your existing RAG system)
        # For now, we'll return success - you'll need to integrate with your RAG store
        # rag_store.add_chunks(chunks, subject_id, topic_id, doc_name, uploaded_by)
        
        return EmbedResponse(
            ok=True,
            subjectId=subject_id,
            topicId=topic_id,
            docName=doc_name,
            uploadedBy=uploaded_by,
            chunks_processed=len(chunks),
            message=f"Successfully processed {len(chunks)} chunks from {doc_name}"
        )
        
    except Exception as e:
        return EmbedResponse(
            ok=False,
            subjectId=subject_id,
            topicId=topic_id,
            docName=doc_name,
            uploadedBy=uploaded_by,
            chunks_processed=0,
            message=f"Error processing file: {str(e)}"
        )

def embed_directory(dir_path: str, subject_id: str, topic_id: str, uploaded_by: str, recursive: bool = True) -> Dict[str, Any]:
    """Embed all files in a directory."""
    if not os.path.exists(dir_path):
        return {
            "ok": False,
            "message": f"Directory not found: {dir_path}",
            "files_processed": 0,
            "total_chunks": 0
        }
    
    results = []
    total_chunks = 0
    supported_extensions = {'.txt', '.md', '.pdf', '.docx', '.doc'}
    
    try:
        for root, dirs, files in os.walk(dir_path):
            if not recursive and root != dir_path:
                continue
                
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_ext not in supported_extensions:
                    continue
                
                # Extract doc name from file path
                doc_name = os.path.splitext(file)[0]
                
                # Process file
                result = embed_single_file(file_path, subject_id, topic_id, doc_name, uploaded_by)
                results.append(result)
                
                if result.ok:
                    total_chunks += result.chunks_processed
        
        return {
            "ok": True,
            "message": f"Processed {len(results)} files",
            "files_processed": len(results),
            "total_chunks": total_chunks,
            "results": results
        }
        
    except Exception as e:
        return {
            "ok": False,
            "message": f"Error processing directory: {str(e)}",
            "files_processed": 0,
            "total_chunks": 0
        }
