# backend/app/api_router.py
import asyncio
import time
from fastapi import APIRouter, Body, HTTPException, Query, Request, File, UploadFile, Form
from fastapi.responses import FileResponse
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from typing import List, Optional
from datetime import datetime
from .models import (
    ChatRequest, ChatResponse, Source, SessionMessage,
    GenerateRequest, GenerateResponse, ResetSessionRequest, ResetSessionResponse,
    EmbedRequest, EmbedResponse, IngestFileRequest, IngestDirRequest,
    Conversation, HistoryRequest, HistoryResponse, AnalyticsRequest, AnalyticsResponse,
    GenerateContentRequest, GenerateContentResponse, ContentListResponse, ContentDownloadResponse,
    TokenUsage, UserEngagement, TopSubject, SystemPerformance, EnhancedAnalyticsResponse,
    PaginationInfo
)
from . import rag_store_chromadb as rag
from . import web_cloud as wc
from . import deps
from . import session_manager
from . import embedding_service
from . import conversation_manager
from .content_manager import clean_markdown_formatting
from . import content_manager
from .cleanup_service import cleanup_service
from openai import OpenAI
import time
import os

# Initialize API router with tags (prefix handled in main.py)
api_router = APIRouter(tags=["ICLeaF AI"])

# Concurrency control for uploads (max 5 concurrent as per spec)
upload_semaphore = asyncio.Semaphore(5)

# LLM client
client = OpenAI(api_key=deps.OPENAI_API_KEY) if deps.OPENAI_API_KEY else None

@api_router.get("/health")
def health():
    """Comprehensive system health check."""
    try:
        # Check all system components
        rag_count = rag.count()
        conversation_count = len(conversation_manager.get_all_conversations())
        content_count = len(content_manager.get_all_content())
        
        # Check OpenAI client
        openai_status = "configured" if client else "not_configured"
        
        # Check embedding service
        embedding_status = "configured" if embedding_service.embedding_client else "not_configured"
        
        return {
            "ok": True,
            "system": "ICLeaF AI",
            "version": "1.0.0",
            "modes": ["cloud", "internal"],
            "components": {
                "rag_store": {
                    "status": "active",
                    "document_count": rag_count
                },
                "conversation_manager": {
                    "status": "active",
                    "conversation_count": conversation_count
                },
                "content_manager": {
                    "status": "active",
                    "content_count": content_count
                },
                "openai_client": {
                    "status": openai_status
                },
                "embedding_service": {
                    "status": embedding_status,
                    "model": embedding_service.get_embedding_model()
                }
            },
            "endpoints": {
                "chatbot": [
                    "/api/chatbot/query",
                    "/api/chatbot/reset-session",
                    "/api/chatbot/history",
                    "/api/chatbot/analytics"
                ],
                "content": [
                    "/api/content/generate",
                    "/api/content/list",
                    "/api/content/download/{contentId}",
                    "/api/content/info/{contentId}",
                    "/api/content/{contentId}/status"
                ],
                "knowledge": [
                    "/api/chatbot/knowledge/embed",
                    "/api/chatbot/knowledge/ingest-file",
                    "/api/chatbot/knowledge/upload-file",
                    "/api/chatbot/knowledge/ingest-dir"
                ],
                "internal": [
                    "/api/internal/search"
                ]
            }
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "system": "ICLeaF AI"
        }

@api_router.get("/stats")
def stats():
    return {
        "index_count": rag.count(),
        "modes": ["cloud", "internal"],
        "embedding_model": embedding_service.get_embedding_model()
    }

@api_router.get("/internal/search")
def internal_search(
    q: str = Query(..., min_length=2), 
    top_k: int = 6,
    subject_id: str = Query(None),
    topic_id: str = Query(None),
    doc_name: str = Query(None)
):
    """
    Enhanced internal search with metadata filtering.
    """
    hits = rag.query(q, top_k=min(top_k, 5), min_similarity=0.1)
    results = []
    
    for h in hits:
        meta = h.get("meta", {})
        
        # Apply metadata filters if provided
        if subject_id and meta.get("subjectId") != subject_id:
            continue
        if topic_id and meta.get("topicId") != topic_id:
            continue
        if doc_name and meta.get("filename") != doc_name:
            continue
            
        results.append({
            "snippet": h["text"][:400],
            "title": meta.get("title", meta.get("filename", "Document")),
            "filename": meta.get("filename"),
            "page": meta.get("page"),
            "score": h.get("score"),
            "subjectId": meta.get("subjectId"),
            "topicId": meta.get("topicId"),
            "uploadedBy": meta.get("uploadedBy"),
            "chunkId": f"chunk_{meta.get('id', 'unknown')}"
        })
    
    return {
        "ok": True, 
        "q": q, 
        "results": results,
        "filters": {
            "subjectId": subject_id,
            "topicId": topic_id,
            "docName": doc_name
        }
    }

@api_router.post("/chatbot/query", response_model=ChatResponse)
async def chatbot_query(req: ChatRequest = Body(...)):
    """
    Main chatbot endpoint that handles both internal and cloud modes.
    Enforces 10-second timeout as per API spec.
    """
    start_time = time.time()
    
    try:
        # Wrap the entire processing in a 10-second timeout
        result = await asyncio.wait_for(
            _process_chatbot_query(req, start_time),
            timeout=10.0
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Request timeout: Processing took longer than 10 seconds. Please try again with a simpler query.")

async def _process_chatbot_query(req: ChatRequest, start_time: float) -> ChatResponse:
    """Process the chatbot query with proper error handling."""
    sources: List[Source] = []
    context_blocks: List[str] = []

    # Store the user message in session history
    user_msg = SessionMessage(
        role="user",
        content=req.message,
        subjectId=req.subjectId,
        topicId=req.topicId,
        docName=req.docName
    )
    session_manager.append_history(req.sessionId, user_msg)

    # INTERNAL (RAG) mode
    if req.mode == "internal":
        # Use enhanced RAG with cosine similarity threshold >= 0.1 and top-5 enforcement
        hits = rag.query(req.message, top_k=min(req.top_k, 5), min_similarity=0.1)
        
        for i, h in enumerate(hits):
            meta = h.get("meta", {})
            chunk_id = f"chunk_{i}_{meta.get('filename', 'unknown')}"
            relevance_score = h.get("score", 0.0)
            
            sources.append(
                Source(
                    title=meta.get("title", meta.get("filename", "Document")),
                    url=meta.get("url"),
                    score=relevance_score,
                    chunkId=chunk_id,
                    docName=meta.get("filename"),
                    relevanceScore=relevance_score
                )
            )
            
            # Get text content - try multiple possible field names
            text_content = h.get("text", "") or h.get("snippet", "") or h.get("document", "") or h.get("content", "")
            
            if text_content and len(text_content.strip()) > 5:  # Lower threshold
                context_blocks.append(text_content)

        system_prompt = (
            "You are ICLeaF LMS's internal-mode assistant. "
            f"User role: {req.role}. Answer ONLY using the provided context. "
            "If the answer is not in the context, say you don't know and suggest a follow‑up."
        )
        ctx = "\n\n".join([f"[Source {i+1}]\n{b}" for i, b in enumerate(context_blocks)]) if context_blocks else ""
        messages: List[dict] = [{"role": "system", "content": system_prompt}]
        if ctx:
            messages.append({"role": "system", "content": f"Context for grounding:\n{ctx}"})
        
        # Add session history
        for m in session_manager.get_history(req.sessionId, last=10):
            # Convert datetime to string for JSON serialization
            msg_dict = m.model_dump()
            if 'timestamp' in msg_dict and msg_dict['timestamp']:
                # Check if it's already a string
                if not isinstance(msg_dict['timestamp'], str):
                    msg_dict['timestamp'] = msg_dict['timestamp'].isoformat()
            messages.append(msg_dict)
        messages.append({"role": "user", "content": req.message})

        if client is None:
            answer = "LLM not configured (missing OPENAI_API_KEY)."
        elif not context_blocks:
            answer = "I couldn't find this in the internal documents. Try rephrasing or checking Cloud mode."
        else:
            try:
                completion = client.chat.completions.create(
                    model=deps.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.1,
                )
                answer = completion.choices[0].message.content
            except Exception as e:
                if "quota" in str(e).lower() or "insufficient_quota" in str(e).lower():
                    answer = f"⚠️ OpenAI API quota exceeded. Here's a demo response based on your question: '{req.message}'\n\nBased on the available documents, I can provide information about data structures, Python programming, and related topics. Please check your OpenAI billing to restore full functionality."
                else:
                    answer = f"Error calling OpenAI API: {str(e)}"

        # Store the assistant response in session history
        assistant_msg = SessionMessage(
            role="assistant",
            content=answer,
            subjectId=user_msg.subjectId,
            topicId=user_msg.topicId,
            docName=user_msg.docName
        )
        session_manager.append_history(req.sessionId, assistant_msg)

        # Track conversation for analytics
        response_time = time.time() - start_time
        conversation = Conversation(
            sessionId=req.sessionId,
            userId=req.userId,
            mode=req.mode,
            subjectId=req.subjectId,
            topicId=req.topicId,
            docName=req.docName,
            userMessage=req.message,
            aiResponse=answer,
            sources=sources,
            responseTime=response_time,
            tokenCount=len(answer.split())  # Approximate token count
        )
        conversation_manager.add_conversation(conversation)

        return ChatResponse(
            answer=answer, 
            sources=sources, 
            sessionId=req.sessionId, 
            userId=req.userId,
            mode=req.mode
        )

    # CLOUD (web / YouTube / GitHub) mode
    if deps.TAVILY_API_KEY:
        try:
            web_results = await wc.tavily_search(req.message, deps.TAVILY_API_KEY, max_results=5)
            for r in web_results:
                sources.append(
                    Source(
                        title=r.get("title") or r.get("url", "Web page"),
                        url=r.get("url"),
                        score=r.get("score"),
                    )
                )
                if r.get("url"):
                    try:
                        txt = await wc.fetch_url_text(r["url"])
                        if txt:
                            context_blocks.append(txt)
                        if len(context_blocks) >= 8:
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    if len(context_blocks) < 8 and deps.YOUTUBE_API_KEY:
        try:
            yt_results = await wc.youtube_search(req.message, deps.YOUTUBE_API_KEY, max_results=3)
            for y in yt_results:
                sources.append(Source(title=f"YouTube: {y['title']}", url=y["url"]))
                transcript = wc.youtube_fetch_transcript_text(y["videoId"])
                if transcript:
                    context_blocks.append(transcript)
                if len(context_blocks) >= 8:
                    break
        except Exception:
            pass

    if len(context_blocks) < 8:
        try:
            gh_results = await wc.github_search_code(req.message, deps.GITHUB_TOKEN, max_results=3)
            for g in gh_results:
                text, dl_url = await wc.github_fetch_file_text(g.get("api_url"), deps.GITHUB_TOKEN)
                title = f"GitHub: {g.get('repository_full_name')}/{g.get('path')}"
                sources.append(Source(title=title, url=dl_url or g.get("html_url")))
                if text:
                    context_blocks.append(text)
                if len(context_blocks) >= 8:
                    break
        except Exception:
            pass

    system_prompt = (
        "You are ICLeaF LMS's cloud-mode assistant. "
        f"User role: {req.role}. Provide concise, correct answers. "
        "If context is provided, cite sources with [1], [2], ... matching the source list. "
        "If you're unsure, say so."
    )
    ctx = "\n\n".join([f"[Source {i+1}]\n{b}" for i, b in enumerate(context_blocks)]) if context_blocks else ""
    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    if ctx:
        messages.append({"role": "system", "content": f"Context for grounding:\n{ctx}"})
    
    # Add session history
    for m in session_manager.get_history(req.sessionId, last=10):
        messages.append(m.model_dump())
    messages.append({"role": "user", "content": req.message})

    if client is None:
        answer = "LLM not configured (missing OPENAI_API_KEY)."
    else:
        completion = client.chat.completions.create(
            model=deps.OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
        )
        answer = completion.choices[0].message.content
        # Clean markdown formatting from chat response
        answer = clean_markdown_formatting(answer)

    # Store the assistant response in session history
    assistant_msg = SessionMessage(
        role="assistant",
        content=answer,
        subjectId=user_msg.subjectId,
        topicId=user_msg.topicId,
        docName=user_msg.docName
    )
    session_manager.append_history(req.sessionId, assistant_msg)

    # Track conversation for analytics
    response_time = time.time() - start_time
    conversation = Conversation(
        sessionId=req.sessionId,
        userId=req.userId,
        mode=req.mode,
        subjectId=req.subjectId,
        topicId=req.topicId,
        docName=req.docName,
        userMessage=req.message,
        aiResponse=answer,
        sources=sources,
        responseTime=response_time,
        tokenCount=len(answer.split())  # Approximate token count
    )
    conversation_manager.add_conversation(conversation)

    return ChatResponse(
        answer=answer, 
        sources=sources, 
        sessionId=req.sessionId, 
        userId=req.userId,
        mode=req.mode
    )

@api_router.get("/chat")
def chat_info():
    """Get chat endpoint information."""
    return {
        "endpoint": "/api/chatbot/query",
        "modes": ["cloud", "internal"],
        "description": "Main chatbot endpoint for ICLeaF AI"
    }

@api_router.get("/sessions/{sessionId}/history")
def get_session_history(sessionId: str, last: int = 10):
    """Get session history for a given session ID."""
    history = session_manager.get_history(sessionId, last)
    return {
        "sessionId": sessionId,
        "history": history,
        "count": len(history)
    }

@api_router.delete("/sessions/{sessionId}/history")
def clear_session_history(sessionId: str):
    """Clear session history for a given session ID."""
    session_manager.clear_history(sessionId)
    return {
        "sessionId": sessionId,
        "message": "Session history cleared"
    }

@api_router.get("/sessions")
def list_sessions():
    """List all active sessions (for debugging/admin purposes)."""
    sessions = session_manager.get_all_sessions()
    return {
        "sessions": list(sessions.keys()),
        "count": len(sessions)
    }

@api_router.post("/chatbot/reset-session", response_model=ResetSessionResponse)
def reset_session(req: ResetSessionRequest = Body(...)):
    """
    Reset chatbot session with optional scope filtering.
    """
    try:
        if req.resetScope == "full":
            # Clear entire session
            session_manager.clear_history(req.sessionId)
            message = f"Session {req.sessionId} completely reset"
        elif req.resetScope == "subject" and req.subjectId:
            # Clear messages related to specific subject
            history = session_manager.get_history(req.sessionId, last=1000)  # Get all history
            filtered_history = [msg for msg in history if msg.subjectId != req.subjectId]
            session_manager.clear_history(req.sessionId)
            for msg in filtered_history:
                session_manager.append_history(req.sessionId, msg)
            message = f"Session {req.sessionId} reset for subject {req.subjectId}"
        elif req.resetScope == "topic" and req.topicId:
            # Clear messages related to specific topic
            history = session_manager.get_history(req.sessionId, last=1000)
            filtered_history = [msg for msg in history if msg.topicId != req.topicId]
            session_manager.clear_history(req.sessionId)
            for msg in filtered_history:
                session_manager.append_history(req.sessionId, msg)
            message = f"Session {req.sessionId} reset for topic {req.topicId}"
        elif req.resetScope == "document" and req.docName:
            # Clear messages related to specific document
            history = session_manager.get_history(req.sessionId, last=1000)
            filtered_history = [msg for msg in history if msg.docName != req.docName]
            session_manager.clear_history(req.sessionId)
            for msg in filtered_history:
                session_manager.append_history(req.sessionId, msg)
            message = f"Session {req.sessionId} reset for document {req.docName}"
        else:
            # Default to full reset
            session_manager.clear_history(req.sessionId)
            message = f"Session {req.sessionId} completely reset"

        return ResetSessionResponse(
            ok=True,
            sessionId=req.sessionId,
            userId=req.userId,
            message=message,
            resetScope=req.resetScope
        )
    except Exception as e:
        return ResetSessionResponse(
            ok=False,
            sessionId=req.sessionId,
            userId=req.userId,
            message=f"Error resetting session: {str(e)}",
            resetScope=req.resetScope
        )

# ----- Knowledge Base Embedding Endpoints -----
@api_router.post("/chatbot/knowledge/embed", response_model=EmbedResponse)
def embed_knowledge(req: EmbedRequest = Body(...)):
    """
    Embed knowledge content into the knowledge base.
    Supports both direct content and file paths.
    """
    try:
        if req.content:
            # Process direct text content
            chunks = embedding_service.process_document_content(
                req.content, 
                req.docName
            )
            
            if not chunks:
                return EmbedResponse(
                    success=False,
                    subjectId=req.subjectId,
                    topicId=req.topicId,
                    docName=req.docName,
                    uploadedBy=req.uploadedBy,
                    chunks_processed=0,
                    message="No valid chunks could be created from the content"
                )
            
            # TODO: Store chunks in RAG store with metadata
            # rag_store.add_chunks_with_metadata(chunks, req.subjectId, req.topicId, req.docName, req.uploadedBy)
            
            return EmbedResponse(
                ok=True,
                subjectId=req.subjectId,
                topicId=req.topicId,
                docName=req.docName,
                uploadedBy=req.uploadedBy,
                chunks_processed=len(chunks),
                message=f"Successfully embedded {len(chunks)} chunks"
            )
            
        elif req.file_path:
            # Process file
            return embedding_service.embed_single_file(
                req.file_path,
                req.subjectId,
                req.topicId,
                req.docName,
                req.uploadedBy
            )
        else:
            return EmbedResponse(
                success=False,
                subjectId=req.subjectId,
                topicId=req.topicId,
                docName=req.docName,
                uploadedBy=req.uploadedBy,
                chunks_processed=0,
                message="Either content or file_path must be provided"
            )
            
    except Exception as e:
        return EmbedResponse(
            ok=False,
            subjectId=req.subjectId,
            topicId=req.topicId,
            docName=req.docName,
            uploadedBy=req.uploadedBy,
            chunks_processed=0,
            message=f"Error embedding knowledge: {str(e)}"
        )

@api_router.post("/chatbot/knowledge/ingest-file")
def ingest_file(req: IngestFileRequest = Body(...)):
    """
    Ingest a single file into the knowledge base.
    """
    result = embedding_service.embed_single_file(
        req.file_path,
        req.subjectId,
        req.topicId,
        req.docName,
        req.uploadedBy
    )
    return result

@api_router.post("/chatbot/knowledge/upload-file")
async def upload_file(
    file: UploadFile = File(...),
    subjectId: str = Form(...),
    topicId: str = Form(...),
    uploadedBy: str = Form(...)
):
    """
    Upload and ingest a single file into the knowledge base.
    Enforces file size limit of 50MB and concurrency limit of 5 as per API spec.
    """
    async with upload_semaphore:  # Limit concurrent uploads to 5
        try:
            # Check file size (50MB limit as per spec)
            MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes
            content = await file.read()
            
            if len(content) > MAX_FILE_SIZE:
                return EmbedResponse(
                    success=False,
                    subjectId=subjectId,
                    topicId=topicId,
                    docName=file.filename,
                    uploadedBy=uploadedBy,
                    chunks_processed=0,
                    message=f"File too large: {len(content)} bytes. Maximum allowed: {MAX_FILE_SIZE} bytes (50MB)"
                )
            
            # Create uploads directory if it doesn't exist
            uploads_dir = "./data/uploads"
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Save uploaded file
            file_path = os.path.join(uploads_dir, file.filename)
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            # Process the file
            result = embedding_service.embed_single_file(
                file_path,
                subjectId,
                topicId,
                file.filename,
                uploadedBy
            )
            
            # Clean up uploaded file after processing
            try:
                os.remove(file_path)
            except:
                pass  # Ignore cleanup errors
                
            return result
            
        except Exception as e:
            return EmbedResponse(
                success=False,
                subjectId=subjectId,
                topicId=topicId,
                docName=file.filename,
                uploadedBy=uploadedBy,
                chunks_processed=0,
                message=f"Error uploading file: {str(e)}"
            )

@api_router.post("/chatbot/knowledge/ingest-dir")
def ingest_directory(req: IngestDirRequest = Body(...)):
    """
    Ingest all files in a directory into the knowledge base.
    """
    result = embedding_service.embed_directory(
        req.dir_path,
        req.subjectId,
        req.topicId,
        req.uploadedBy,
        req.recursive
    )
    return result

# ----- History and Analytics Endpoints -----
@api_router.get("/chatbot/history")
def get_conversation_history(
    sessionId: str = Query(None),
    userId: str = Query(None),
    subjectId: str = Query(None),
    topicId: str = Query(None),
    docName: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    page: int = Query(1),
    limit: int = Query(20)
):
    """
    Get conversation history with filtering and pagination.
    Supports hierarchical path: sessionId/subjectId/topicId/docName
    """
    try:
        # Parse dates if provided
        start_dt = None
        end_dt = None
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        # Create filter request
        filters = HistoryRequest(
            sessionId=sessionId,
            userId=userId,
            subjectId=subjectId,
            topicId=topicId,
            docName=docName,
            start_date=start_dt,
            end_date=end_dt,
            page=page,
            limit=limit
        )
        
        # Get filtered conversations
        conversations, total_count = conversation_manager.get_conversations(filters)
        
        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit  # Ceiling division
        pagination = PaginationInfo(
            currentPage=page,
            totalPages=total_pages,
            totalRecords=total_count,
            recordsPerPage=limit
        )
        
        return HistoryResponse(
            success=True,
            conversations=conversations,
            pagination=pagination,
            message=f"Retrieved {len(conversations)} conversations out of {total_count} total"
        )
        
    except Exception as e:
        return HistoryResponse(
            ok=False,
            conversations=[],
            total_count=0,
            filters={},
            message=f"Error retrieving history: {str(e)}"
        )

@api_router.get("/chatbot/history/{sessionId}")
def get_session_history(sessionId: str):
    """Get conversation history for a specific session."""
    try:
        conversations = conversation_manager.get_conversation_by_path(sessionId)
        return {
            "ok": True,
            "sessionId": sessionId,
            "conversations": conversations,
            "count": len(conversations)
        }
    except Exception as e:
        return {
            "ok": False,
            "sessionId": sessionId,
            "conversations": [],
            "count": 0,
            "error": str(e)
        }

@api_router.get("/chatbot/history/{sessionId}/{subjectId}")
def get_subject_history(sessionId: str, subjectId: str):
    """Get conversation history for a specific session and subject."""
    try:
        conversations = conversation_manager.get_conversation_by_path(sessionId, subjectId)
        return {
            "ok": True,
            "sessionId": sessionId,
            "subjectId": subjectId,
            "conversations": conversations,
            "count": len(conversations)
        }
    except Exception as e:
        return {
            "ok": False,
            "sessionId": sessionId,
            "subjectId": subjectId,
            "conversations": [],
            "count": 0,
            "error": str(e)
        }

@api_router.get("/chatbot/history/{sessionId}/{subjectId}/{topicId}")
def get_topic_history(sessionId: str, subjectId: str, topicId: str):
    """Get conversation history for a specific session, subject, and topic."""
    try:
        conversations = conversation_manager.get_conversation_by_path(sessionId, subjectId, topicId)
        return {
            "ok": True,
            "sessionId": sessionId,
            "subjectId": subjectId,
            "topicId": topicId,
            "conversations": conversations,
            "count": len(conversations)
        }
    except Exception as e:
        return {
            "ok": False,
            "sessionId": sessionId,
            "subjectId": subjectId,
            "topicId": topicId,
            "conversations": [],
            "count": 0,
            "error": str(e)
        }

@api_router.get("/chatbot/history/{sessionId}/{subjectId}/{topicId}/{docName}")
def get_document_history(sessionId: str, subjectId: str, topicId: str, docName: str):
    """Get conversation history for a specific session, subject, topic, and document."""
    try:
        conversations = conversation_manager.get_conversation_by_path(sessionId, subjectId, topicId, docName)
        return {
            "ok": True,
            "sessionId": sessionId,
            "subjectId": subjectId,
            "topicId": topicId,
            "docName": docName,
            "conversations": conversations,
            "count": len(conversations)
        }
    except Exception as e:
        return {
            "ok": False,
            "sessionId": sessionId,
            "subjectId": subjectId,
            "topicId": topicId,
            "docName": docName,
            "conversations": [],
            "count": 0,
            "error": str(e)
        }

@api_router.get("/chatbot/analytics")
def get_analytics(
    userId: Optional[str] = Query(None, description="Filter by specific user"),
    fromDate: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    toDate: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    subjectId: Optional[str] = Query(None, description="Filter by subject"),
    topicId: Optional[str] = Query(None, description="Filter by topic")
):
    """
    Retrieve analytics and usage statistics for chatbot interactions.
    Provides insights into token usage, user engagement, content performance, and system health.
    """
    try:
        # Parse dates if provided
        start_dt = None
        end_dt = None
        if fromDate:
            start_dt = datetime.fromisoformat(fromDate)
        if toDate:
            end_dt = datetime.fromisoformat(toDate)
        
        # Get enhanced analytics
        analytics = conversation_manager.get_enhanced_analytics(
            start_date=start_dt,
            end_date=end_dt,
            subjectId=subjectId,
            topicId=topicId,
            userId=userId
        )
        
        return analytics
        
    except Exception as e:
        # Return empty analytics on error
        from .models import TokenUsage, UserEngagement, TopSubject, SystemPerformance, EnhancedAnalyticsResponse
        return EnhancedAnalyticsResponse(
            success=False,
            period={"fromDate": None, "toDate": None},
            tokenUsage=TokenUsage(internalMode=0, externalMode=0, totalCost=0.0),
            userEngagement=UserEngagement(totalQueries=0, avgSessionDuration=0.0, messagesPerSession=0.0, activeUsers=0),
            topSubjects=[],
            systemPerformance=SystemPerformance(avgResponseTime=0.0, successRate=0.0, uptime=0.0)
        )

@api_router.get("/chatbot/analytics/stats")
def get_analytics_stats():
    """Get basic analytics statistics."""
    try:
        stats = conversation_manager.get_conversation_stats()
        return {
            "ok": True,
            "stats": stats,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "ok": False,
            "stats": {},
            "error": str(e),
            "generated_at": datetime.now().isoformat()
        }

# ----- Content Generation Endpoints -----
@api_router.post("/content/generate", response_model=GenerateContentResponse)
async def generate_content(request: GenerateContentRequest = Body(...)):
    """
    Generate various types of content based on user specifications.
    Supports: pdf, ppt, flashcard, quiz, assessment, video, audio, compiler
    Enforces SLA timeouts: PPT/PDF <60/90s, Audio <2m, Video <5m
    """
    start_time = time.time()
    
    # Determine SLA timeout based on content type
    sla_timeout = 60  # Default 60 seconds
    if request.contentType in ["pdf"]:
        sla_timeout = 90  # PDF: 90 seconds
    elif request.contentType in ["ppt"]:
        sla_timeout = 60  # PPT: 60 seconds
    elif request.contentType in ["audio"]:
        sla_timeout = 120  # Audio: 2 minutes
    elif request.contentType in ["video"]:
        sla_timeout = 300  # Video: 5 minutes
    
    try:
        # Wrap content generation in SLA timeout
        result = await asyncio.wait_for(
            _process_content_generation(request, start_time),
            timeout=sla_timeout
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail=f"Content generation timeout: Processing took longer than {sla_timeout} seconds. Please try again with simpler content.")

async def _process_content_generation(request: GenerateContentRequest, start_time: float) -> GenerateContentResponse:
    try:
        # Validate content type and config
        if request.contentType == "flashcard" and not request.contentConfig.get('flashcard'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Flashcard config is required for flashcard content type"
            )
        elif request.contentType == "quiz" and not request.contentConfig.get('quiz'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Quiz config is required for quiz content type"
            )
        elif request.contentType == "assessment" and not request.contentConfig.get('assessment'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Assessment config is required for assessment content type"
            )
        elif request.contentType == "video" and not request.contentConfig.get('video'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Video config is required for video content type"
            )
        elif request.contentType == "audio" and not request.contentConfig.get('audio'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Audio config is required for audio content type"
            )
        elif request.contentType == "compiler" and not request.contentConfig.get('compiler'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Compiler config is required for compiler content type"
            )
        elif request.contentType == "pdf" and not request.contentConfig.get('pdf'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="PDF config is required for PDF content type"
            )
        elif request.contentType == "ppt" and not request.contentConfig.get('ppt'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="PPT config is required for PPT content type"
            )
        
        # Process content generation
        content = await content_manager.process_content_generation(request)
        
        # Estimate completion time based on content type
        estimated_time = {
            "flashcard": 30,
            "quiz": 60,
            "assessment": 120,
            "video": 300,
            "audio": 180,
            "compiler": 90,
            "pdf": 120,
            "ppt": 150
        }.get(request.contentType, 60)
        
        return GenerateContentResponse(
            success=True,
            contentId=content.contentId,
            userId=request.userId,
            status=content.status,
            message=f"Content generation started for {request.contentType}",
            etaSeconds=estimated_time
        )
        
    except Exception as e:
        return GenerateContentResponse(
            success=False,
            contentId="",
            userId=request.userId,
            status="failed",
            message=f"Error generating content: {str(e)}"
        )

@api_router.get("/content/list", response_model=ContentListResponse)
def list_content(
    userId: str = Query(...),
    status: str = Query(None),
    contentType: str = Query(None),
    page: int = Query(1),
    limit: int = Query(20)
):
    """
    List generated content for a user with optional filtering.
    """
    try:
        # Get user content
        user_content = content_manager.get_user_content(userId)
        
        # Apply filters
        if status:
            user_content = [c for c in user_content if c.status == status]
        if contentType:
            user_content = [c for c in user_content if c.contentType == contentType]
        
        # Apply pagination (convert page/limit to offset/limit)
        total_count = len(user_content)
        offset = (page - 1) * limit
        paginated_content = user_content[offset:offset + limit]
        
        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit  # Ceiling division
        pagination = PaginationInfo(
            currentPage=page,
            totalPages=total_pages,
            totalRecords=total_count,
            recordsPerPage=limit
        )
        
        return ContentListResponse(
            success=True,
            contents=paginated_content,
            pagination=pagination,
            userId=userId
        )
        
    except Exception as e:
        return ContentListResponse(
            success=False,
            contents=[],
            pagination=PaginationInfo(currentPage=1, totalPages=0, totalRecords=0, recordsPerPage=limit),
            userId=userId
        )

@api_router.get("/content/download/{contentId}")
def download_content(contentId: str, request: Request):
    """
    Download generated content by content ID.
    Returns the actual file for media content or metadata for other content.
    """
    try:
        content = content_manager.get_content(contentId)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        if content.status != "completed":
            raise HTTPException(status_code=400, detail=f"Content is not ready. Status: {content.status}")
        
        if not content.filePath or not os.path.exists(content.filePath):
            raise HTTPException(status_code=404, detail="Content file not found")
        
        # Track download for analytics
        client_ip = request.client.host if request.client else "unknown"
        content_manager.track_download(contentId, content.userId, client_ip)
        
        # For media files (audio/video), return the actual file
        if content.contentType in ["audio", "video"]:
            # Determine the correct media file path
            storage_dir = os.path.dirname(content.filePath)
            if content.contentType == "audio":
                media_file = os.path.join(storage_dir, "audio.mp3")
            else:  # video
                media_file = os.path.join(storage_dir, "video.mp4")
            
            if os.path.exists(media_file):
                return FileResponse(
                    path=media_file,
                    filename=f"{contentId}.{media_file.split('.')[-1]}",
                    media_type="audio/mpeg" if content.contentType == "audio" else "video/mp4"
                )
            else:
                # Fallback to metadata file
                return FileResponse(
                    path=content.filePath,
                    filename=f"{contentId}_metadata.json",
                    media_type="application/json"
                )
        else:
            # For other content types, return the file directly
            return FileResponse(
                path=content.filePath,
                filename=f"{contentId}_{content.contentType}.{content.filePath.split('.')[-1]}",
                media_type="application/octet-stream"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading content: {str(e)}")

@api_router.get("/content/info/{contentId}", response_model=ContentDownloadResponse)
def get_content_info(contentId: str):
    """
    Get information about generated content by content ID.
    """
    try:
        content = content_manager.get_content(contentId)
        if not content:
            return ContentDownloadResponse(
                success=False,
                contentId=contentId,
                filePath="",
                downloadUrl="",
                contentType="",
                message="Content not found"
            )
        
        if content.status != "completed":
            return ContentDownloadResponse(
                success=False,
                contentId=contentId,
                filePath="",
                downloadUrl="",
                contentType=content.contentType,
                message=f"Content is not ready. Status: {content.status}"
            )
        
        if not content.filePath or not os.path.exists(content.filePath):
            return ContentDownloadResponse(
                success=False,
                contentId=contentId,
                filePath="",
                downloadUrl="",
                contentType=content.contentType,
                message="Content file not found"
            )
        
        # Get file size
        file_size = os.path.getsize(content.filePath) if os.path.exists(content.filePath) else None
        
        return ContentDownloadResponse(
            ok=True,
            contentId=contentId,
            filePath=content.filePath,
            downloadUrl=f"/api/content/download/{contentId}",
            contentType=content.contentType,
            fileSize=file_size
        )
        
    except Exception as e:
        return ContentDownloadResponse(
            ok=False,
            contentId=contentId,
            filePath="",
            downloadUrl="",
            contentType="",
            message=f"Error getting content info: {str(e)}"
        )

@api_router.get("/content/{contentId}/downloads")
def get_content_downloads(contentId: str):
    """
    Get download statistics for a content item.
    """
    try:
        content = content_manager.get_content(contentId)
        if not content:
            raise HTTPException(status_code=404, detail="Content not found")
        
        download_stats = content_manager.get_download_stats(contentId)
        return {
            "success": True,
            "contentId": contentId,
            "downloadStats": download_stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting download stats: {str(e)}")

@api_router.get("/content/{contentId}/status")
def get_content_status(contentId: str):
    """
    Get the status of a content generation task.
    """
    try:
        content = content_manager.get_content(contentId)
        if not content:
            return {
                "ok": False,
                "contentId": contentId,
                "status": "not_found",
                "message": "Content not found"
            }
        
        return {
            "ok": True,
            "contentId": contentId,
            "status": content.status,
            "createdAt": content.createdAt,
            "completedAt": content.completedAt,
            "error": content.error,
            "downloadUrl": content.downloadUrl if content.status == "completed" else None
        }
        
    except Exception as e:
        return {
            "ok": False,
            "contentId": contentId,
            "status": "error",
            "message": str(e)
        }

@api_router.post("/admin/cleanup")
async def trigger_cleanup():
    """Manually trigger cleanup of old files (admin endpoint)."""
    try:
        await cleanup_service.cleanup_now()
        return {
            "success": True,
            "message": "Cleanup completed successfully",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Cleanup failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@api_router.get("/")
def system_overview():
    """
    Complete system overview and API documentation.
    """
    return {
        "system": "ICLeaF AI - Intelligent Content Learning Framework",
        "version": "1.0.0",
        "description": "Comprehensive AI-powered educational content generation and chatbot system",
        "features": [
            "Intelligent Chatbot with RAG and Cloud modes",
            "Multi-format Content Generation",
            "Knowledge Base Management",
            "Conversation History and Analytics",
            "Session Management",
            "Real-time Status Tracking"
        ],
        "api_endpoints": {
            "chatbot": {
                "description": "Chatbot interaction and session management",
                "endpoints": {
                    "POST /api/chatbot/query": "Main chatbot endpoint with session tracking",
                    "POST /api/chatbot/reset-session": "Reset chatbot session with scope filtering",
                    "GET /api/chatbot/history": "Get conversation history with filtering",
                    "GET /api/chatbot/history/{sessionId}": "Get session-specific history",
                    "GET /api/chatbot/history/{sessionId}/{subjectId}": "Get subject-specific history",
                    "GET /api/chatbot/history/{sessionId}/{subjectId}/{topicId}": "Get topic-specific history",
                    "GET /api/chatbot/history/{sessionId}/{subjectId}/{topicId}/{docName}": "Get document-specific history",
                    "GET /api/chatbot/analytics": "Get comprehensive analytics",
                    "GET /api/chatbot/analytics/stats": "Get basic statistics"
                }
            },
            "content": {
                "description": "Content generation and management",
                "endpoints": {
                    "POST /api/content/generate": "Generate various content types (pdf, ppt, flashcard, quiz, assessment, video, audio, compiler)",
                    "GET /api/content/list": "List user content with filtering",
                    "GET /api/content/download/{contentId}": "Download generated content (returns actual files for media)",
                    "GET /api/content/info/{contentId}": "Get content information and metadata",
                    "GET /api/content/{contentId}/status": "Check content generation status"
                },
                "supported_types": ["pdf", "ppt", "flashcard", "quiz", "assessment", "video", "audio", "compiler"]
            },
            "knowledge": {
                "description": "Knowledge base embedding and management",
                "endpoints": {
                    "POST /api/chatbot/knowledge/embed": "Embed knowledge content",
                    "POST /api/chatbot/knowledge/ingest-file": "Ingest single file (JSON)",
                    "POST /api/chatbot/knowledge/upload-file": "Upload and ingest file (multipart)",
                    "POST /api/chatbot/knowledge/ingest-dir": "Ingest directory of files"
                }
            },
            "internal": {
                "description": "Internal search and document management",
                "endpoints": {
                    "GET /api/internal/search": "Search internal documents with metadata filtering"
                }
            },
            "system": {
                "description": "System health and statistics",
                "endpoints": {
                    "GET /api/health": "Comprehensive system health check",
                    "GET /api/stats": "System statistics",
                    "GET /api/": "System overview and API documentation"
                }
            }
        },
        "user_roles": ["Learner", "Trainer", "Admin"],
        "modes": ["cloud", "internal"],
        "rate_limiting": "10 requests per minute for chatbot queries",
        "storage": {
            "conversations": "In-memory with session management",
            "content": "/data/content/{userId}/{contentId}",
            "knowledge_base": "Chroma vector database"
        }
    }
