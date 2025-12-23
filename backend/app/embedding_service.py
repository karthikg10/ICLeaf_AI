# backend/app/embedding_service.py
import os
import hashlib
import uuid
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI
from . import deps
from . import rag_store_chromadb as rag
from .models import EmbedRequest, EmbedResponse, IngestFileRequest, IngestDirRequest
from .ingest_dir import _read_file_build_docs

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

def embed_texts_batch(texts: List[str], model: str = None, batch_size: int = 100) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts using OpenAI batch API.
    
    Args:
        texts: List of text strings to embed
        model: Embedding model name (defaults to text-embedding-3-small)
        batch_size: Number of texts to process per API call (OpenAI supports up to 2048)
        
    Returns:
        List of embeddings (same order as input texts), None for failed embeddings
    """
    if not embedding_client or not texts:
        return [None] * len(texts) if texts else []
    
    model = model or get_embedding_model()
    all_embeddings: List[Optional[List[float]]] = []
    
    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        try:
            print(f"[RAG] Generating embeddings batch {batch_num}/{total_batches} ({len(batch_texts)} texts)...", end="\r")
            response = embedding_client.embeddings.create(
                input=batch_texts,  # Pass list of texts for batch processing
                model=model
            )
            
            # Extract embeddings in order
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            
        except Exception as e:
            print(f"\n[RAG] Error generating batch embeddings: {e}")
            # Add None for each failed text in this batch
            all_embeddings.extend([None] * len(batch_texts))
    
    print()  # New line after progress
    return all_embeddings

def process_document_content(content: str, doc_name: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict[str, Any]]:
    """Process document content into chunks with embeddings using token-based chunking."""
    if not content.strip():
        return []
    
    # Split content into chunks using token-based approach
    chunks = []
    words = content.split()
    
    # Approximate token count (roughly 1.3 tokens per word for English)
    tokens_per_word = 1.3
    token_chunk_size = int(chunk_size / tokens_per_word)
    token_overlap = int(overlap / tokens_per_word)
    
    for i in range(0, len(words), token_chunk_size - token_overlap):
        chunk_words = words[i:i + token_chunk_size]
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
                "chunk_size": len(chunk_text),
                "estimated_tokens": int(len(chunk_text.split()) * tokens_per_word)
            }
        })
    
    return chunks

def embed_single_file(file_path: str, subject_id: str, topic_id: str, doc_name: str, uploaded_by: str) -> EmbedResponse:
    """Embed a single file into the knowledge base and store in ChromaDB."""
    try:
        if not os.path.exists(file_path):
            return EmbedResponse(
                ok=False,
                subjectId=subject_id,
                topicId=topic_id,
                docName=doc_name,
                uploadedBy=uploaded_by,
                chunks_processed=0,
                message=f"File not found: {file_path}",
                docId=None
            )
        
        # Use ingest_dir logic to read different file types (PDF, DOCX, TXT, etc.)
        docs = _read_file_build_docs(file_path)
        
        if not docs:
            return EmbedResponse(
                ok=False,
                subjectId=subject_id,
                topicId=topic_id,
                docName=doc_name,
                uploadedBy=uploaded_by,
                chunks_processed=0,
                message="File is empty, unreadable, or unsupported format",
                docId=None
            )
        
        # Generate unique document ID for this file
        doc_id = str(uuid.uuid4())
        
        # Prepare documents for ChromaDB with metadata
        chroma_docs: List[Tuple[str, Dict]] = []
        for chunk_text, meta in docs:
            # Enhance metadata with upload information
            enhanced_meta = meta.copy()
            enhanced_meta["subjectId"] = subject_id
            enhanced_meta["topicId"] = topic_id
            enhanced_meta["docName"] = doc_name or meta.get("filename", os.path.basename(file_path))
            enhanced_meta["uploadedBy"] = uploaded_by
            enhanced_meta["filename"] = meta.get("filename", os.path.basename(file_path))
            enhanced_meta["title"] = meta.get("title", enhanced_meta.get("filename", "Document"))
            enhanced_meta["source"] = "upload"
            enhanced_meta["docId"] = doc_id  # Add unique document ID
            
            chroma_docs.append((chunk_text, enhanced_meta))
        
        # Store in ChromaDB RAG store
        if chroma_docs:
            try:
                rag.add_documents(chroma_docs)
                print(f"[embed] Successfully stored {len(chroma_docs)} chunks from {doc_name} in ChromaDB with docId: {doc_id}")
            except Exception as e:
                print(f"[embed] Error storing in ChromaDB: {e}")
                return EmbedResponse(
                    ok=False,
                    subjectId=subject_id,
                    topicId=topic_id,
                    docName=doc_name,
                    uploadedBy=uploaded_by,
                    chunks_processed=0,
                    message=f"Error storing in ChromaDB: {str(e)}",
                    docId=None
                )
        
        return EmbedResponse(
            ok=True,
            subjectId=subject_id,
            topicId=topic_id,
            docName=doc_name,
            uploadedBy=uploaded_by,
            chunks_processed=len(chroma_docs),
            message=f"Successfully processed and stored {len(chroma_docs)} chunks from {doc_name} in ChromaDB",
            docId=doc_id
        )
        
    except Exception as e:
        return EmbedResponse(
            ok=False,
            subjectId=subject_id,
            topicId=topic_id,
            docName=doc_name,
            uploadedBy=uploaded_by,
            chunks_processed=0,
            message=f"Error processing file: {str(e)}",
            docId=None
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
