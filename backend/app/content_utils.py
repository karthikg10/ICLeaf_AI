# backend/app/content_utils.py
# Shared utilities for content generation
import os
import uuid
import re
from typing import Dict, List, Optional, Any, NamedTuple
from datetime import datetime
from .models import GeneratedContent, GenerateContentRequest, ContentStatus
from . import rag_store_chromadb as rag
from . import deps
from openai import OpenAI

# In-memory content storage (in production, use database)
_content_storage: Dict[str, GeneratedContent] = {}

# Download tracking (in production, use database)
_download_tracking: Dict[str, List[Dict]] = {}  # contentId -> [{"timestamp": ..., "userId": ..., "ip": ...}]

# Content generation client
content_client = OpenAI(api_key=deps.OPENAI_API_KEY) if deps.OPENAI_API_KEY else None


class RAGContextResult(NamedTuple):
    """Result from RAG context retrieval, containing the context string and metadata about documents used."""
    context: str
    metadata: Dict[str, Any]  # Contains: documents_used (list of docIds/filenames), num_blocks, requested_docIds, is_relevant, avg_similarity


def validate_rag_context_for_internal_mode(rag_result: RAGContextResult, request: GenerateContentRequest) -> None:
    """Validate that relevant context exists for internal mode content generation.
    
    Raises ValueError with descriptive error message if context is empty or irrelevant.
    """
    if request.mode != "internal":
        return  # Only validate for internal mode
    
    rag_context = rag_result.context
    rag_metadata = rag_result.metadata
    
    if not rag_context or not rag_metadata.get("is_relevant", False):
        error_msg = (
            f"No relevant information found in the specified documents for the topic '{request.prompt}'. "
        )
        if request.docIds and len(request.docIds) > 0:
            error_msg += (
                f"The requested document(s) do not contain relevant content about this topic. "
                f"Please ensure the document(s) contain information related to '{request.prompt}' "
                f"or try a different topic that matches the document content."
            )
        else:
            error_msg += (
                "No relevant documents found in your uploaded documents. "
                "Please upload documents that contain information related to this topic."
            )
        raise ValueError(error_msg)


def extract_openai_response(response):
    """Safely extract content from OpenAI API response with full debugging."""
    try:
        # FIRST: Check if response has error
        if hasattr(response, 'error') and response.error is not None:
            error_detail = response.error
            print(f"[ERROR] OpenAI returned error: {error_detail}")
            raise ValueError(f"OpenAI API Error: {error_detail}")
        
        # SECOND: Check choices exist
        if not hasattr(response, 'choices'):
            print(f"[ERROR] Response has no 'choices' attribute")
            print(f"[DEBUG] Response attributes: {list(vars(response).keys())}")
            raise ValueError("Response missing 'choices'")
        
        if len(response.choices) == 0:
            print(f"[ERROR] Response.choices is empty")
            raise ValueError("No choices in response")
        
        print(f"[DEBUG] ✓ Response has {len(response.choices)} choices")
        
        # THIRD: Get first choice
        choice = response.choices[0]
        
        if not hasattr(choice, 'message'):
            print(f"[ERROR] Choice has no 'message' attribute")
            print(f"[DEBUG] Choice type: {type(choice)}")
            print(f"[DEBUG] Choice attributes: {list(vars(choice).keys())}")
            raise ValueError("Choice missing 'message'")
        
        print(f"[DEBUG] ✓ Choice has message")
        
        # FOURTH: Get message
        message = choice.message
        
        if not hasattr(message, 'content'):
            print(f"[ERROR] Message has no 'content' attribute")
            print(f"[DEBUG] Message type: {type(message)}")
            print(f"[DEBUG] Message attributes: {list(vars(message).keys())}")
            raise ValueError("Message missing 'content'")
        
        print(f"[DEBUG] ✓ Message has content")
        
        # FIFTH: Get content
        content = message.content
        
        if not content:
            print(f"[ERROR] Content is empty or None")
            raise ValueError("Content is empty")
        
        if not isinstance(content, str):
            print(f"[ERROR] Content is not string, it's {type(content)}")
            content = str(content)
        
        print(f"[DEBUG] ✓ Got content: {len(content)} characters")
        return content
        
    except ValueError as e:
        print(f"[ERROR] ValueError: {str(e)}")
        raise
    except Exception as e:
        print(f"[ERROR] Unexpected error: {type(e).__name__}: {str(e)}")
        raise ValueError(f"Failed to extract response: {str(e)}")


def validate_custom_path(custom_path: str) -> bool:
    """Validate custom file path for security."""
    if not custom_path:
        return True
    
    # Prevent directory traversal
    if ".." in custom_path:
        raise ValueError("Invalid path: directory traversal (..) not allowed")
    
    if custom_path.startswith("/etc") or custom_path.startswith("/sys"):
        raise ValueError("Invalid path: system directories not allowed")
    
    return True


def generate_content_id() -> str:
    """Generate a unique content ID."""
    return str(uuid.uuid4())


def clean_markdown_formatting(text: str) -> str:
    """Remove markdown formatting from text, but preserve **bold** for headings."""
    
    # Keep **bold** formatting (for headings/subheadings) - don't remove it
    # Remove __ (alternative bold syntax)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = text.replace('__', '')
    
    # Remove * and _ (italic) - but be careful with contractions
    text = re.sub(r'([^a-zA-Z0-9])\*(.*?)\*([^a-zA-Z0-9])', r'\1\2\3', text)
    text = re.sub(r'([^a-zA-Z0-9])_(.*?)_([^a-zA-Z0-9])', r'\1\2\3', text)
    
    # Remove ` (inline code)
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    # Remove ``` (code blocks)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    
    # Remove # (headers)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    # Remove - (lists) - replace with just text
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    
    # Remove > (blockquotes)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    
    # Remove [text](url) links - keep just text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove --- (horizontal rules)
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
    
    # Remove | (tables)
    text = re.sub(r'\|.*\|', '', text)
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Max 2 newlines
    text = re.sub(r' +', ' ', text)  # Single spaces
    text = text.strip()
    
    return text


def get_rag_context_for_internal_mode(request: GenerateContentRequest, top_k: int = 5) -> RAGContextResult:
    """Get RAG context from uploaded documents for internal mode content generation.
    
    If docIds are provided, filters results to only include chunks from those documents.
    Returns a RAGContextResult containing the context string and metadata about documents used.
    """
    if request.mode != "internal":
        return RAGContextResult(context="", metadata={"documents_used": [], "num_blocks": 0, "requested_docIds": []})
    
    try:
        # Query RAG store with the prompt
        # Use 0.3 as min_similarity threshold to ensure relevance
        # This prevents returning irrelevant chunks when topics don't match
        
        # If docIds are provided, we need to query for each docId separately
        # because rag.query() only supports filtering by a single doc_name
        all_hits = []
        requested_doc_ids = []
        documents_found = set()  # Track which documents were actually found and used
        QUERY_MIN_SIMILARITY = 0.1  # Lower threshold for initial query to get results, then validate average
        
        # Query-length aware thresholds
        query_tokens = len(request.prompt.split())
        has_specific_doc = request.docIds and len(request.docIds) > 0
        
        # When filtering by specific docId, use very permissive threshold to get all chunks from that doc
        # Then validate similarity afterward - this ensures we get results even if individual similarities are low
        DOC_ID_QUERY_MIN_SIMILARITY = -0.2 if has_specific_doc else QUERY_MIN_SIMILARITY
        
        # Set thresholds based on query length and whether specific doc is selected
        if query_tokens <= 3:
            # Short query: more lenient thresholds
            MIN_RELEVANCE_THRESHOLD = 0.15
            MAX_SIM_THRESHOLD = 0.25
            # If specific doc is selected, be even more lenient
            if has_specific_doc:
                MIN_RELEVANCE_THRESHOLD = 0.12
                MAX_SIM_THRESHOLD = 0.22
        else:
            # Longer query: stricter thresholds
            MIN_RELEVANCE_THRESHOLD = 0.2
            MAX_SIM_THRESHOLD = 0.3
            # If specific doc is selected, slightly more lenient
            if has_specific_doc:
                MIN_RELEVANCE_THRESHOLD = 0.18
                MAX_SIM_THRESHOLD = 0.28
        
        print(f"[CONTENT] Query length: {query_tokens} tokens, Specific doc: {has_specific_doc}, Thresholds: avg>={MIN_RELEVANCE_THRESHOLD}, max>={MAX_SIM_THRESHOLD}")
        
        if request.docIds and len(request.docIds) > 0:
            # Filter by specific documents
            doc_ids_set = set(doc_id.strip() for doc_id in request.docIds if doc_id and doc_id.strip())
            requested_doc_ids = list(doc_ids_set)
            print(f"[CONTENT] Internal mode: Filtering by docIds: {requested_doc_ids}")
            
            # Query each document separately and combine results
            hits_per_doc = max(1, top_k // len(doc_ids_set))  # Distribute top_k across documents
            
            for doc_id in doc_ids_set:
                try:
                    doc_hits = []
                    # First try filtering by docId (UUID) if it looks like a UUID
                    # Otherwise try by doc_name/filename (legacy support)
                    # Use very permissive threshold when filtering by specific docId to ensure we get results
                    # Then validate similarity afterward
                    if len(doc_id) == 36 and doc_id.count('-') == 4:  # UUID format
                        doc_hits = rag.query(
                            request.prompt,
                            top_k=hits_per_doc,
                            min_similarity=DOC_ID_QUERY_MIN_SIMILARITY,  # Very permissive when docId specified
                            doc_id=doc_id
                        )
                    else:
                        # Legacy: filter by doc_name or filename
                        doc_hits = rag.query(
                            request.prompt,
                            top_k=hits_per_doc,
                            min_similarity=DOC_ID_QUERY_MIN_SIMILARITY,  # Very permissive when docId specified
                            doc_name=doc_id
                        )
                    
                    if doc_hits:
                        # Track which documents were found
                        for hit in doc_hits:
                            meta = hit.get("meta", {})
                            doc_id_used = meta.get("docId", "") or meta.get("docName", "") or meta.get("filename", "")
                            if doc_id_used:
                                documents_found.add(doc_id_used)
                        all_hits.extend(doc_hits)
                        print(f"[CONTENT] Found {len(doc_hits)} chunks from docId '{doc_id}'")
                    else:
                        print(f"[CONTENT] No relevant chunks found for docId '{doc_id}' (query similarity threshold: {DOC_ID_QUERY_MIN_SIMILARITY})")
                except Exception as e:
                    print(f"[CONTENT] Error querying docId '{doc_id}': {e}")
                    continue
            
            # NO FALLBACK - if no results from specified documents, return empty
            # This ensures we don't generate content from irrelevant or wrong documents
        else:
            # No docIds specified, query all documents
            all_hits = rag.query(
                request.prompt,
                top_k=top_k,
                min_similarity=QUERY_MIN_SIMILARITY  # Lower threshold to get results, then validate average
            )
            # Track all documents found
            for hit in all_hits:
                meta = hit.get("meta", {})
                doc_id_used = meta.get("docId", "") or meta.get("docName", "") or meta.get("filename", "")
                if doc_id_used:
                    documents_found.add(doc_id_used)
        
        if not all_hits:
            print(f"[CONTENT] Internal mode: No relevant context retrieved from RAG query")
            return RAGContextResult(
                context="",
                metadata={
                    "documents_used": [],
                    "num_blocks": 0,
                    "requested_docIds": requested_doc_ids,
                    "internal_mode": True,
                    "rag_used": False,
                    "is_relevant": False,
                    "avg_similarity": 0.0
                }
            )
        
        # Use top-k hits for relevance stats (top 3-5) to avoid weak trailing chunks dragging down average
        TOP_K_FOR_STATS = min(5, len(all_hits))
        top_hits = sorted(all_hits, key=lambda x: x.get("score", 0.0), reverse=True)[:TOP_K_FOR_STATS]
        similarity_scores = [hit.get("score", 0.0) for hit in top_hits if hit.get("score") is not None]
        
        avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
        min_similarity = min(similarity_scores) if similarity_scores else 0.0
        max_similarity = max(similarity_scores) if similarity_scores else 0.0
        
        print(f"[CONTENT] Top-{TOP_K_FOR_STATS} stats - Average: {avg_similarity:.3f}, Min: {min_similarity:.3f}, Max: {max_similarity:.3f}")
        
        # Validate relevance: 
        # If specific docId is selected and we got hits, skip threshold check (user explicitly selected this doc)
        # Otherwise, accept if average meets threshold OR if max similarity is high
        if has_specific_doc and len(all_hits) > 0:
            is_relevant = True
            print(f"[CONTENT] Specific docId selected with {len(all_hits)} hits - skipping similarity threshold validation")
        else:
            # Validate relevance: accept if average meets threshold OR if max similarity is high (at least one highly relevant chunk)
            # This helps with short queries where average might be lower but top chunks are still relevant
            is_relevant = avg_similarity >= MIN_RELEVANCE_THRESHOLD or max_similarity >= MAX_SIM_THRESHOLD
        
        if not is_relevant:
            print(f"[CONTENT] Context relevance check failed: avg_similarity {avg_similarity:.3f} < {MIN_RELEVANCE_THRESHOLD} AND max_similarity {max_similarity:.3f} < {MAX_SIM_THRESHOLD}")
            return RAGContextResult(
                context="",
                metadata={
                    "documents_used": [],
                    "num_blocks": 0,
                    "requested_docIds": requested_doc_ids,
                    "internal_mode": True,
                    "rag_used": False,
                    "is_relevant": False,
                    "avg_similarity": avg_similarity
                }
            )
        
        # Clean and extract context from hits
        context_blocks = []
        seen_texts = set()  # Deduplicate context blocks
        
        for h in all_hits:
            text_content = h.get("text", "")
            if not text_content or not isinstance(text_content, str):
                continue
            
            # Clean the text
            text_content = clean_markdown_formatting(text_content)
            text_content = text_content.strip()
            
            if not text_content:
                continue
            
            # Remove excessive whitespace
            text_content = " ".join(text_content.split())
            
            # Deduplicate: skip if we've seen this exact text before
            text_hash = hash(text_content[:200])  # Hash first 200 chars for deduplication
            if text_hash in seen_texts:
                continue
            seen_texts.add(text_hash)
            
            context_blocks.append(text_content)
            
            # Limit to top_k blocks
            if len(context_blocks) >= top_k:
                break
        
        if not context_blocks:
            print(f"[CONTENT] No valid context blocks extracted from hits")
            return RAGContextResult(
                context="",
                metadata={
                    "documents_used": [],
                    "num_blocks": 0,
                    "requested_docIds": requested_doc_ids,
                    "internal_mode": True,
                    "rag_used": False,
                    "is_relevant": False,
                    "avg_similarity": avg_similarity
                }
            )
        
        # Build context string
        ctx_parts = []
        for i, block in enumerate(context_blocks, 1):
            ctx_parts.append(f"[Content Block {i}]\n{block}")
        
        context = "\n\n---\n\n".join(ctx_parts)
        doc_info = f" from {len(request.docIds)} specified documents" if request.docIds else ""
        print(f"[CONTENT] Internal mode: Retrieved {len(context_blocks)} relevant context blocks{doc_info} from uploaded documents")
        print(f"[CONTENT] Documents used: {list(documents_found)}")
        
        return RAGContextResult(
            context=context,
            metadata={
                "documents_used": list(documents_found),
                "num_blocks": len(context_blocks),
                "is_relevant": True,
                "avg_similarity": avg_similarity,
                "requested_docIds": requested_doc_ids,
                "internal_mode": True,
                "rag_used": True
            }
        )
        
    except Exception as e:
        print(f"[CONTENT] Error getting RAG context: {e}")
        return RAGContextResult(
            context="",
            metadata={
                "documents_used": [],
                "num_blocks": 0,
                "requested_docIds": requested_doc_ids if 'requested_doc_ids' in locals() else [],
                "internal_mode": True,
                "rag_used": False,
                "error": str(e)
            }
        )


def get_content_storage_path(user_id: str, content_id: str) -> str:
    """Get the storage path for content."""
    return f"/data/content/{user_id}/{content_id}"


def create_content_directory(user_id: str, content_id: str) -> str:
    """Create directory for content storage."""
    base_path = f"./data/content/{user_id}/{content_id}"
    os.makedirs(base_path, exist_ok=True)
    return base_path


def store_content(content: GeneratedContent) -> None:
    """Store content in memory and optionally on disk."""
    _content_storage[content.contentId] = content


def get_content(content_id: str) -> Optional[GeneratedContent]:
    """Get content by ID."""
    return _content_storage.get(content_id)


def get_user_content(user_id: str, status: Optional[ContentStatus] = None) -> List[GeneratedContent]:
    """Get all content for a user, optionally filtered by status."""
    user_content = [c for c in _content_storage.values() if c.userId == user_id]
    if status:
        user_content = [c for c in user_content if c.status == status]
    return sorted(user_content, key=lambda x: x.createdAt, reverse=True)


def update_content_status(content_id: str, status: ContentStatus, file_path: str = None, error: str = None) -> None:
    """Update content status."""
    if content_id in _content_storage:
        content = _content_storage[content_id]
        content.status = status
        if file_path:
            content.filePath = file_path
            content.downloadUrl = f"/api/content/download/{content_id}"
        if error:
            content.error = error
        if status == "completed":
            content.completedAt = datetime.now()

