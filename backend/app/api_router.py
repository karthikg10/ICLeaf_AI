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
from .content_utils import clean_markdown_formatting
from . import content_manager
from .cleanup_service import cleanup_service
from .query_clarifier import evaluate_query_for_clarification
from .conversation_context import expand_query_with_context, get_conversation_summary
from openai import OpenAI
import time
import os
import uuid


# Disable ChromaDB telemetry
os.environ["CHROMA_TELEMETRY_ENABLED"] = "False"

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
    hits = rag.query(q, top_k=min(top_k, 5), min_similarity=-0.2)
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

@api_router.options("/chatbot/query")
async def chatbot_query_options(request: Request):
    """Handle OPTIONS preflight requests for CORS."""
    from fastapi.responses import Response
    # Return empty response with 200 status - CORS middleware will add headers
    return Response(status_code=200, content="")

@api_router.post("/chatbot/query", response_model=ChatResponse)
async def chatbot_query(req: ChatRequest = Body(...)):
    """
    Main chatbot endpoint that handles both internal and cloud modes.
    Enforces 10-second timeout as per API spec.
    """
    print("Hello from chatbot_query.")
    start_time = time.time()
    print(f"[CHATBOT] Received query: '{req.message[:50]}...' in mode: {req.mode}")
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
    print
    sources: List[Source] = []
    context_blocks: List[str] = []

    # Accept the provided sessionId and userId (already validated as NonEmptyStr in ChatRequest)
    # Ensure the userId has a mapping to this sessionId for consistency
    session_manager.ensure_user_session_mapping(req.userId, req.sessionId)
    
    # Store the user message in session history using the provided sessionId
    user_msg = SessionMessage(
        role="user",
        content=req.message,
        subjectId=req.subjectId,
        topicId=req.topicId,
        docName=req.docName
    )
    session_manager.append_history(req.sessionId, user_msg)

    # Get conversation history for clarification check
    conversation_history = session_manager.get_history(req.sessionId, last=10)

    # Early clarification step shared by both internal and external modes.
    # Pass history so it can skip clarification for follow-ups and confirmations
    clarification = evaluate_query_for_clarification(req.message, conversation_history)
    if clarification.should_clarify:
        answer = clarification.message or (
            "I want to be sure I understand your request. Could you rephrase it?"
        )

        assistant_msg = SessionMessage(
            role="assistant",
            content=answer,
            subjectId=user_msg.subjectId,
            topicId=user_msg.topicId,
            docName=user_msg.docName
        )
        session_manager.append_history(req.sessionId, assistant_msg)

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
            sources=[],
            responseTime=response_time,
            tokenCount=len(answer.split())
        )
        conversation_manager.add_conversation(conversation)

        return ChatResponse(
            answer=answer,
            sources=[],
            sessionId=req.sessionId,
            mode=req.mode
        )
    # INTERNAL (RAG) mode - FIXED VERSION

    # INTERNAL (RAG) mode
    if req.mode == "internal":
        # Get conversation history for context expansion
        conversation_history = session_manager.get_history(req.sessionId, last=10)
        
        # Expand query with context if it's a follow-up question
        search_query, was_expanded = expand_query_with_context(req.message, conversation_history)
        if was_expanded:
            print(f"[CHATBOT] Expanded query for context: '{req.message}' -> '{search_query[:100]}...'")
        
        # Apply metadata filters if provided
        subject_id_filter = req.subjectId if req.subjectId else None
        topic_id_filter = req.topicId if req.topicId else None
        doc_name_filter = req.docName if req.docName else None

        # Query-length aware settings (use original message for token count)
        query_tokens = len(req.message.split())
        has_specific_doc = bool(req.docIds and len(req.docIds) > 0)
        
        # Base similarity thresholds (used only when NO specific docId)
        # More lenient thresholds for shorter queries, gradually stricter for longer ones
        if query_tokens <= 3:
            MIN_RELEVANCE_THRESHOLD = 0.15
            MAX_SIM_THRESHOLD = 0.25
        elif query_tokens <= 8:
            # Medium-length queries: more lenient thresholds
            MIN_RELEVANCE_THRESHOLD = 0.16  # Lower from 0.18
            MAX_SIM_THRESHOLD = 0.26        # Lower from 0.28
        else:
            # Longer queries: stricter thresholds
            MIN_RELEVANCE_THRESHOLD = 0.18
            MAX_SIM_THRESHOLD = 0.28
        
        # Retrieval thresholds
        QUERY_MIN_SIMILARITY = -0.2
        DOC_ID_QUERY_MIN_SIMILARITY = -0.2 if has_specific_doc else QUERY_MIN_SIMILARITY
        
        print(f"[CHATBOT] Query length: {query_tokens} tokens, Specific doc: {has_specific_doc}, Thresholds: avg>={MIN_RELEVANCE_THRESHOLD}, max>={MAX_SIM_THRESHOLD}")

        # Handle docIds filtering (similar to content generation)
        hits = []
        if has_specific_doc:
            # Filter by specific documents
            doc_ids_set = set(doc_id.strip() for doc_id in req.docIds if doc_id and doc_id.strip())
            print(f"[CHATBOT] Internal mode: Filtering by docIds: {list(doc_ids_set)}")
            
            # Query each document separately and combine results
            hits_per_doc = max(1, min(req.top_k, 5) // len(doc_ids_set))
            all_hits = []
            
            for doc_id in doc_ids_set:
                try:
                    # UUID-style docId vs legacy filename
                    if len(doc_id) == 36 and doc_id.count('-') == 4:  # UUID format
                        doc_hits = rag.query(
                            search_query,  # Use expanded query for better context
                            top_k=hits_per_doc,
                            min_similarity=DOC_ID_QUERY_MIN_SIMILARITY,  # VERY permissive
                            subject_id=subject_id_filter,
                            topic_id=topic_id_filter,
                            doc_id=doc_id
                        )
                    else:
                        # Legacy: filter by doc_name or filename
                        doc_hits = rag.query(
                            search_query,  # Use expanded query for better context
                            top_k=hits_per_doc,
                            min_similarity=DOC_ID_QUERY_MIN_SIMILARITY,  # VERY permissive
                            subject_id=subject_id_filter,
                            topic_id=topic_id_filter,
                            doc_name=doc_id
                        )
                    
                    if doc_hits:
                        all_hits.extend(doc_hits)
                        print(f"[CHATBOT] Found {len(doc_hits)} chunks from docId '{doc_id}'")
                    else:
                        print(f"[CHATBOT] No chunks found for docId '{doc_id}'")
                except Exception as e:
                    print(f"[CHATBOT] Error querying docId '{doc_id}': {e}")
                    continue
            
            hits = all_hits
        else:
            # No docIds specified, normal query
            hits = rag.query(
                search_query,  # Use expanded query for better context
                top_k=min(req.top_k, 5),
                min_similarity=QUERY_MIN_SIMILARITY,
                subject_id=subject_id_filter,
                topic_id=topic_id_filter,
                doc_name=doc_name_filter
            )

        print(f"[CHATBOT] Internal mode query: '{req.message[:50]}...'")
        print(f"[CHATBOT] Found {len(hits)} RAG hits")

        # Use top-k hits for relevance stats (top 3-5) to avoid weak trailing chunks dragging down average
        TOP_K_FOR_STATS = min(5, len(hits))
        top_hits = sorted(hits, key=lambda x: x.get("score", 0.0), reverse=True)[:TOP_K_FOR_STATS]
        similarity_scores = [hit.get("score", 0.0) for hit in top_hits if hit.get("score") is not None]
        
        avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
        min_similarity = min(similarity_scores) if similarity_scores else 0.0
        max_similarity = max(similarity_scores) if similarity_scores else 0.0
        
        print(f"[CHATBOT] Top-{TOP_K_FOR_STATS} stats - Average: {avg_similarity:.3f}, Min: {min_similarity:.3f}, Max: {max_similarity:.3f}")
        
        # Relevance check:
        # 1) If user selected a specific docId and we got ANY hits, trust the user and accept them.
        # 2) Otherwise, use thresholds based on avg / max similarity with fallback.
        if has_specific_doc and len(hits) > 0:
            print(f"[CHATBOT] Specific docId selected with {len(hits)} hits - skipping similarity threshold validation")
            is_relevant = True
        else:
            if not similarity_scores:
                is_relevant = False
            else:
                is_relevant = (
                    avg_similarity >= MIN_RELEVANCE_THRESHOLD
                    or max_similarity >= MAX_SIM_THRESHOLD
                    or max_similarity >= 0.20  # Fallback: if max is decent, accept
                )
        
        if not is_relevant:
            print(f"[CHATBOT] Context relevance check failed: avg_similarity {avg_similarity:.3f} < {MIN_RELEVANCE_THRESHOLD} AND max_similarity {max_similarity:.3f} < {MAX_SIM_THRESHOLD}")
            # Return "information not found" response without sources
            answer = "I couldn't find relevant information about this topic in the provided documents. Please try rephrasing your question or check if the topic is covered in the documents."
            assistant_msg = SessionMessage(
                role="assistant",
                content=answer,
                subjectId=user_msg.subjectId,
                topicId=user_msg.topicId,
                docName=user_msg.docName
            )
            session_manager.append_history(req.sessionId, assistant_msg)
            
            return ChatResponse(
                success=True,
                answer=answer,
                sources=[],  # No sources if not relevant
                sessionId=req.sessionId,
                mode=req.mode,
                timestamp=datetime.now().isoformat()
            )

        # After getting RAG content, CLEAN IT
        for hit in hits:
            # Remove ** from hit text
            hit["text"] = clean_markdown_formatting(hit["text"])

        # ===== FIX #1: Extract context FIRST, validate, THEN add source =====
        # ===== FIX #2: Deduplicate sources by document name =====
        
        seen_documents = {}  # Track documents we've already added as sources
        
        for i, h in enumerate(hits):
            meta = h.get("meta", {})
            text_content = h.get("text", "")
            filename = meta.get("filename", "unknown")
            relevance_score = h.get("score", 0.0)
            
            # STEP 1: Validate text content EXISTS and has meaningful length
            if not text_content or not isinstance(text_content, str):
                print(f"[CHATBOT] Skipped hit {i+1}: No text content")
                continue
                
            # Clean up text
            text_content = text_content.strip()
            if not text_content:
                print(f"[CHATBOT] Skipped hit {i+1}: Empty after strip")
                continue
            
            # Remove excessive whitespace but keep all content
            text_content = " ".join(text_content.split())
            
            # STEP 2: Add context block (synchronized with source)
            context_blocks.append(text_content)
            print(f"[CHATBOT] Added context block {len(context_blocks)}: {len(text_content)} chars, score: {relevance_score:.3f}")
            
            # STEP 3: Add source ONLY if we haven't seen this document before
            # This deduplicate sources by document name
            if filename not in seen_documents:
                chunk_id = f"chunk_{i}_{filename}"
                source = Source(
                    title=meta.get("title", meta.get("filename", "Document")),
                    url=meta.get("url"),
                    score=relevance_score,
                    chunkId=chunk_id,
                    docName=filename,
                    relevanceScore=relevance_score
                )
                sources.append(source)
                seen_documents[filename] = True
                print(f"[CHATBOT] Added unique source: {filename}")
            else:
                print(f"[CHATBOT] Skipped duplicate source: {filename} (already in sources)")

        print(f"[CHATBOT] Total context blocks: {len(context_blocks)}")
        print(f"[CHATBOT] Total unique sources: {len(sources)}")
        print(f"[CHATBOT] Total context length: {sum(len(b) for b in context_blocks)} chars")

        # ===== FIX #3: Always build context, with fallback for empty blocks =====
        if context_blocks:
            # Build context with sources
            ctx_parts = []
            for i, block in enumerate(context_blocks, 1):
                # Include blocks without citation markers
                ctx_parts.append(block)
            ctx = "\n\n---\n\n".join(ctx_parts)
        else:
            # Only use this message if we found NO valid content
            ctx = "No relevant context found in the documents."

        # Get conversation summary for context
        conversation_summary = get_conversation_summary(conversation_history)
        context_note = ""
        if conversation_summary:
            context_note = f"\n\nPREVIOUS CONVERSATION CONTEXT:\n{conversation_summary}\n\nUse this context to understand references like 'it', 'its', 'the topic', etc. in the user's question."
        
        # Build system prompt with context
        system_prompt = f"""You are ICLeaF LMS's internal-mode assistant helping students learn from documents.

    INSTRUCTIONS:
    1. Answer ONLY using the provided context below
    2. Be helpful and educational
    3. Do NOT include citations, references, or content block markers in your response
    4. Use **bold** markdown formatting ONLY for headings and subheadings (e.g., **Heading**, **Subheading**)
    5. Do NOT use other markdown formatting (no __, no *, no #, no lists with -, no code blocks)
    6. Write in plain text for body content, use **bold** only for headings/subheadings
    7. If context is provided but seems insufficient, still give your best answer based on it
    8. IMPORTANT: Use the conversation history below to understand follow-up questions. If the user asks about "it", "its", "the topic", etc., refer to the previous conversation context to understand what they're referring to.

    CONTEXT ({len(context_blocks)} blocks, {len(sources)} sources):
    {ctx}{context_note}

    Now answer the user's question (use **bold** for headings and subheadings only):"""

    #     system_prompt = f"""You are ICLeaF LMS's internal-mode assistant. Your role is to help {req.role}s learn from the provided document context.

    # CRITICAL INSTRUCTIONS:

    # 1. You MUST answer ONLY using the information provided in the context below

    # 2. If the answer is in the context, provide a detailed, helpful answer citing the source

    # 3. If the answer is partially in context, provide what you can and note any limitations

    # 4. If the answer is NOT in the context, say: "I couldn't find this information in the provided documents. Please try rephrasing your question."

    # 5. Always cite your sources

    # 6. Be helpful, clear, and educational

    # PROVIDED CONTEXT ({len(context_blocks)} content blocks from {len(sources)} unique documents):

    # {ctx}

    # Now answer the user's question USING ONLY the context above."""

        # Build messages list
        messages: List[dict] = [
            {"role": "system", "content": system_prompt}
        ]

        # Add session history (last 5 messages)
        history_messages = session_manager.get_history(req.sessionId, last=5)
        for m in history_messages:
            msg_dict = m.model_dump()
            if msg_dict.get("role") and msg_dict.get("content"):
                messages.append({
                    "role": msg_dict["role"],
                    "content": msg_dict["content"]
                })

        # Add current user message
        messages.append({"role": "user", "content": req.message})

        print(f"[CHATBOT] Total messages: {len(messages)}")
        print(f"[CHATBOT] Context length: {len(ctx)} chars")
        print(f"[CHATBOT] Unique sources: {len(sources)}")

        # Call OpenAI API
        if client is None:
            answer = (
                "⚠️ OpenAI API key is not configured. "
                "Please set OPENAI_API_KEY in your .env file and restart the server."
            )
        elif not context_blocks:
            answer = (
                f"I found {len(hits)} relevant document chunk(s), but couldn't extract meaningful content from them. "
                "This might be a temporary issue. Please try rephrasing your question or checking if the topic is covered in the documents."
            )
        else:
            try:
                print(f"[CHATBOT] Calling OpenAI API with {len(messages)} messages...")
                completion = client.chat.completions.create(
                    model=deps.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1000,
                )
                
                # CORRECT: Extract from the nested structure
                choice = completion.choices[0]  # Get first choice from list
                message = choice.message
                answer = message.content
                
                # Validation
                if not answer:
                    answer = "⚠️ OpenAI returned an empty response. Please try again."
                    print(f"[CHATBOT] WARNING: Empty response from OpenAI")
                else:
                    print(f"[CHATBOT] Received answer: {len(answer)} characters")
                    
            except IndexError:
                print(f"[CHATBOT] No choices in response")
                answer = "⚠️ OpenAI returned no response choices. Please try again."
                
            except AttributeError as e:
                print(f"[CHATBOT] Response structure error: {e}")
                print(f"[CHATBOT] Response: {completion}")
                answer = f"⚠️ Error extracting response: {str(e)}"
                
            except Exception as e:
                error_str = str(e)
                print(f"[CHATBOT] API Error: {error_str}")
    
 

        # Store assistant response
        assistant_msg = SessionMessage(
            role="assistant",
            content=answer,
            subjectId=user_msg.subjectId,
            topicId=user_msg.topicId,
            docName=user_msg.docName
        )
        session_manager.append_history(req.sessionId, assistant_msg)

        # Track conversation
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
            tokenCount=len(answer.split())
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
    print(f"[CHATBOT] Cloud mode query: '{req.message[:50]}...'")
    
    # Get conversation history for context expansion
    conversation_history = session_manager.get_history(req.sessionId, last=10)
    
    # Expand query with context if it's a follow-up question
    search_query, was_expanded = expand_query_with_context(req.message, conversation_history)
    if was_expanded:
        print(f"[CHATBOT] Expanded query for context: '{req.message}' -> '{search_query[:100]}...'")
    
    if deps.TAVILY_API_KEY:
        try:
            web_results = await wc.tavily_search(search_query, deps.TAVILY_API_KEY, max_results=5)  # Use expanded query
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
            print(f"[CHATBOT] Added {len([s for s in sources if 'YouTube' not in s.title and 'GitHub' not in s.title])} web sources from Tavily")
        except Exception as e:
            print(f"[CHATBOT] Tavily search error: {e}")

    if len(context_blocks) < 8 and deps.YOUTUBE_API_KEY:
        try:
            yt_results = await wc.youtube_search(search_query, deps.YOUTUBE_API_KEY, max_results=3)  # Use expanded query
            for y in yt_results:
                sources.append(Source(title=f"YouTube: {y['title']}", url=y["url"]))
                transcript = wc.youtube_fetch_transcript_text(y["videoId"])
                if transcript:
                    context_blocks.append(transcript)
                if len(context_blocks) >= 8:
                    break
            print(f"[CHATBOT] Added {len([s for s in sources if 'YouTube' in s.title])} YouTube sources")
        except Exception as e:
            print(f"[CHATBOT] YouTube search error: {e}")

    if len(context_blocks) < 8:
        try:
            gh_results = await wc.github_search_code(search_query, deps.GITHUB_TOKEN, max_results=3)  # Use expanded query
            for g in gh_results:
                text, dl_url = await wc.github_fetch_file_text(g.get("api_url"), deps.GITHUB_TOKEN)
                title = f"GitHub: {g.get('repository_full_name')}/{g.get('path')}"
                sources.append(Source(title=title, url=dl_url or g.get("html_url")))
                if text:
                    context_blocks.append(text)
                if len(context_blocks) >= 8:
                    break
            print(f"[CHATBOT] Added {len([s for s in sources if 'GitHub' in s.title])} GitHub sources")
        except Exception as e:
            print(f"[CHATBOT] GitHub search error: {e}")
    
    print(f"[CHATBOT] Total sources collected: {len(sources)}")
    print(f"[CHATBOT] Total context blocks: {len(context_blocks)}")

    # Get conversation summary for context
    conversation_summary = get_conversation_summary(conversation_history)
    context_note = ""
    if conversation_summary:
        context_note = f"\n\nPREVIOUS CONVERSATION CONTEXT:\n{conversation_summary}\n\nUse this context to understand references like 'it', 'its', 'the topic', etc. in the user's question. If the user asks about 'it', 'its pros', 'the topic', etc., refer to the previous conversation to understand what they're referring to."
    
    system_prompt = (
        "You are ICLeaF LMS's cloud-mode assistant. "
        f"User role: {req.role}. Provide concise, correct answers. "
        "If context is provided, cite sources with [1], [2], ... matching the source list. "
        "If you're unsure, say so. "
        "IMPORTANT: Use the conversation history below to understand follow-up questions. "
        "If the user asks about 'it', 'its', 'the topic', etc., refer to the previous conversation context to understand what they're referring to."
        + context_note
    )
    ctx = "\n\n".join([f"[Source {i+1}]\n{b}" for i, b in enumerate(context_blocks)]) if context_blocks else ""
    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    if ctx:
        messages.append({"role": "system", "content": f"Context for grounding:\n{ctx}"})
    
    # Accept the provided sessionId and userId (already validated as NonEmptyStr in ChatRequest)
    # Ensure the userId has a mapping to this sessionId for consistency
    session_manager.ensure_user_session_mapping(req.userId, req.sessionId)
    
    # Add session history
    for m in session_manager.get_history(req.sessionId, last=10):
        messages.append(m.model_dump())
    messages.append({"role": "user", "content": req.message})

    if client is None:
        answer = (
            "⚠️ OpenAI API key is not configured. "
            "Please set OPENAI_API_KEY in your .env file and restart the server. "
            "The API key should start with 'sk-' and be a valid OpenAI key."
        )
    else:
        try:
            completion = client.chat.completions.create(
                model=deps.OPENAI_MODEL,
                messages=messages,
                temperature=0.2,
            )
            answer = completion.choices[0].message.content
            # Clean markdown formatting from chat response
            answer = clean_markdown_formatting(answer)
        except Exception as e:
            error_str = str(e)
            if "Invalid API key" in error_str or "incorrect API key" in error_str.lower():
                answer = (
                    "⚠️ Invalid OpenAI API key detected. "
                    "Please check your .env file and ensure OPENAI_API_KEY is set correctly. "
                    "The API key should start with 'sk-' and be a valid OpenAI key. "
                    "After updating, restart the server."
                )
            elif "quota" in error_str.lower() or "insufficient_quota" in error_str.lower():
                answer = "⚠️ OpenAI API quota exceeded. Please check your OpenAI account billing to restore functionality."
            else:
                answer = f"⚠️ Error calling OpenAI API: {error_str}. Please check your API key and network connection."

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

    print(f"[CHATBOT] Returning response with {len(sources)} sources")
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
        # Check if file_path is provided and not empty - prioritize file_path over content
        if req.file_path and isinstance(req.file_path, str) and req.file_path.strip():
            # Process file
            return embedding_service.embed_single_file(
                req.file_path,
                req.subjectId,
                req.topicId,
                req.docName,
                req.uploadedBy
            )
        elif req.content and isinstance(req.content, str) and req.content.strip():
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
                    message="No valid chunks could be created from the content",
                    docId=None
                )
            
            # Generate unique document ID for this content
            doc_id = str(uuid.uuid4())
            
            # Convert chunks to ChromaDB format (list of tuples: (text, metadata))
            chroma_docs = []
            for chunk in chunks:
                meta = {
                    "filename": req.docName or "direct_content",
                    "title": req.docName or "Direct Content",
                    "subjectId": req.subjectId,
                    "topicId": req.topicId,
                    "docName": req.docName,
                    "uploadedBy": req.uploadedBy,
                    "chunk_index": chunk.get("metadata", {}).get("chunk_index", 0),
                    "source": "direct_embed",
                    "docId": doc_id  # Add unique document ID
                }
                chroma_docs.append((chunk["text"], meta))
            
            # Store in ChromaDB RAG store
            if chroma_docs:
                try:
                    rag.add_documents(chroma_docs)
                    print(f"[embed] Successfully stored {len(chroma_docs)} chunks from direct content in ChromaDB with docId: {doc_id}")
                except Exception as e:
                    print(f"[embed] Error storing in ChromaDB: {e}")
                    return EmbedResponse(
                        ok=False,
                        subjectId=req.subjectId,
                        topicId=req.topicId,
                        docName=req.docName,
                        uploadedBy=req.uploadedBy,
                        chunks_processed=0,
                        message=f"Error storing in ChromaDB: {str(e)}",
                        docId=None
                    )
            
            return EmbedResponse(
                ok=True,
                subjectId=req.subjectId,
                topicId=req.topicId,
                docName=req.docName,
                uploadedBy=req.uploadedBy,
                chunks_processed=len(chroma_docs),
                message=f"Successfully embedded and stored {len(chroma_docs)} chunks in ChromaDB",
                docId=doc_id
            )
        else:
            return EmbedResponse(
                success=False,
                subjectId=req.subjectId,
                topicId=req.topicId,
                docName=req.docName,
                uploadedBy=req.uploadedBy,
                chunks_processed=0,
                message="Either content or file_path must be provided (and not empty)",
                docId=None
            )
            
    except Exception as e:
        return EmbedResponse(
            ok=False,
            subjectId=req.subjectId,
            topicId=req.topicId,
            docName=req.docName,
            uploadedBy=req.uploadedBy,
            chunks_processed=0,
            message=f"Error embedding knowledge: {str(e)}",
            docId=None
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
    """Upload and ingest a single file into the knowledge base."""
    async with upload_semaphore:  # Limit concurrent uploads to 5
        try:
            # Check file size (50MB limit as per spec)
            MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes
            content = await file.read()
            
            if len(content) > MAX_FILE_SIZE:
                return {
                    "success": False,
                    "message": f"File too large: {len(content)} bytes. Maximum allowed: {MAX_FILE_SIZE} bytes (50MB)",
                    "contentId": None
                }
            
            # Create uploads directory if it doesn't exist
            uploads_dir = "./data/uploads"
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Verify directory exists and is writable
            if not os.path.isdir(uploads_dir):
                os.makedirs(uploads_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            safe_filename = os.path.basename(file.filename) if file.filename else "uploaded_file"
            
            # Remove any path separators for security
            safe_filename = safe_filename.replace("/", "_").replace("\\", "_")
            
            # Create unique filename
            unique_filename = f"{timestamp}_{unique_id}_{safe_filename}"
            file_path = os.path.join(uploads_dir, unique_filename)
            
            print(f"[UPLOAD] Saving file to: {file_path}")
            
            # Save file
            with open(file_path, "wb") as f:
                f.write(content)
            
            print(f"[UPLOAD] File saved successfully: {file_path}")
            
            # Verify file was saved
            if not os.path.exists(file_path):
                print(f"[ERROR] File was not saved properly!")
                return {
                    "success": False,
                    "message": "File was not saved properly",
                    "contentId": None
                }
            
            # Process the file for embedding
            result = embedding_service.embed_single_file(
                file_path,
                subjectId,
                topicId,
                file.filename,
                uploadedBy
            )
            
            print(f"[UPLOAD] Processing result: {result}")
            
            return {
                "success": result.ok if hasattr(result, 'ok') else result.success,
                "message": result.message if hasattr(result, 'message') else f"File uploaded and processed: {file.filename}",
                "filePath": file_path,
                "filename": safe_filename,
                "contentId": unique_filename,
                "docId": result.docId if hasattr(result, 'docId') else None,  # Return the docId from embedding
                "subjectId": result.subjectId if hasattr(result, 'subjectId') else subjectId,
                "topicId": result.topicId if hasattr(result, 'topicId') else topicId,
                "docName": result.docName if hasattr(result, 'docName') else file.filename,
                "chunks_processed": result.chunks_processed if hasattr(result, 'chunks_processed') else 0
            }
        
        except Exception as e:
            print(f"[ERROR] Upload failed: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "message": f"Error uploading file: {str(e)}",
                "contentId": None
            }

@api_router.get("/chatbot/knowledge/uploads/check")
def check_uploads_directory():
    """Check if uploads directory is working."""
    try:
        uploads_dir = "./data/uploads"
        
        # Check if directory exists
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir, exist_ok=True)
        
        # List files in directory
        files = os.listdir(uploads_dir) if os.path.isdir(uploads_dir) else []
        
        # Check if directory is writable
        test_file = os.path.join(uploads_dir, ".test_write")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            is_writable = True
        except:
            is_writable = False
        
        return {
            "ok": True,
            "directory": os.path.abspath(uploads_dir),
            "exists": os.path.isdir(uploads_dir),
            "is_writable": is_writable,
            "file_count": len(files),
            "files": files[:10]  # Show first 10 files
        }
    
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }

@api_router.get("/chatbot/knowledge/documents")
def list_all_documents():
    """List all uploaded documents with their docIds."""
    try:
        documents = rag.list_all_documents()
        return {
            "ok": True,
            "count": len(documents),
            "documents": documents
        }
    except Exception as e:
        print(f"[ERROR] Failed to list documents: {e}")
        import traceback
        traceback.print_exc()
        return {
            "ok": False,
            "error": str(e),
            "count": 0,
            "documents": []
        }



# @api_router.post("/chatbot/knowledge/upload-file")
# async def upload_file(
#     file: UploadFile = File(...),
#     subjectId: str = Form(...),
#     topicId: str = Form(...),
#     uploadedBy: str = Form(...)
# ):
#     """
#     Upload and ingest a single file into the knowledge base.
#     Enforces file size limit of 50MB and concurrency limit of 5 as per API spec.
#     """
#     async with upload_semaphore:  # Limit concurrent uploads to 5
#         try:
#             # Check file size (50MB limit as per spec)
#             MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes
#             content = await file.read()
            
#             if len(content) > MAX_FILE_SIZE:
#                 return EmbedResponse(
#                     success=False,
#                     subjectId=subjectId,
#                     topicId=topicId,
#                     docName=file.filename,
#                     uploadedBy=uploadedBy,
#                     chunks_processed=0,
#                     message=f"File too large: {len(content)} bytes. Maximum allowed: {MAX_FILE_SIZE} bytes (50MB)"
#                 )
            
#             # Create uploads directory if it doesn't exist
#             uploads_dir = "./data/uploads"
#             os.makedirs(uploads_dir, exist_ok=True)
            
#             # Generate unique filename to avoid conflicts
#             # Format: timestamp_uuid_original_filename
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             unique_id = str(uuid.uuid4())[:8]
#             safe_filename = os.path.basename(file.filename) if file.filename else "uploaded_file"
#             # Remove any path separators from filename for security
#             safe_filename = safe_filename.replace("/", "_").replace("\\", "_")
            
#             # Create unique filename: timestamp_uuid_originalname.ext
#             # This preserves the original file extension and avoids conflicts
#             unique_filename = f"{timestamp}_{unique_id}_{safe_filename}"
#             file_path = os.path.join(uploads_dir, unique_filename)
            
#             # Save uploaded file permanently
#             with open(file_path, "wb") as buffer:
#                 buffer.write(content)
            
#             print(f"[UPLOAD] Saved file to: {file_path} (original: {file.filename})")
            
#             # Process the file for embedding
#             result = embedding_service.embed_single_file(
#                 file_path,
#                 subjectId,
#                 topicId,
#                 file.filename,  # Use original filename for metadata
#                 uploadedBy
#             )
            
#             # File is kept in /uploads directory for future reference
#             # No cleanup - files persist as per requirement
            
#             return result
            
#         except Exception as e:
#             return EmbedResponse(
#                 success=False,
#                 subjectId=subjectId,
#                 topicId=topicId,
#                 docName=file.filename,
#                 uploadedBy=uploadedBy,
#                 chunks_processed=0,
#                 message=f"Error uploading file: {str(e)}"
#             )

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
def get_analytics():
    """Get analytics - simplified version."""
    try:
        # Just return mock data for now
        return {
            "success": True,
            "period": {"fromDate": None, "toDate": None},
            "tokenUsage": {
                "internalMode": 5000,
                "externalMode": 3000,
                "total": 8000,
                "estimatedCost": 0.016
            },
            "userEngagement": {
                "totalQueries": 55,
                "uniqueUsers": 12,
                "avgResponseTime": 1.2,
                "avgQueryLength": 15
            },
            "topSubjects": [
                {"subject": "Data Structures", "queries": 25},
                {"subject": "Algorithms", "queries": 18},
                {"subject": "Python", "queries": 12}
            ],
            "systemPerformance": {
                "avgResponseTime": 1.2,
                "successRate": 95.5,
                "totalRequests": 55
            },
            "generatedAt": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[ERROR] Analytics error: {e}")
        # Still return valid response even on error
        return {
            "success": True,
            "period": {"fromDate": None, "toDate": None},
            "tokenUsage": {"internalMode": 0, "externalMode": 0, "total": 0, "estimatedCost": 0},
            "userEngagement": {"totalQueries": 0, "uniqueUsers": 0, "avgResponseTime": 0, "avgQueryLength": 0},
            "topSubjects": [],
            "systemPerformance": {"avgResponseTime": 0, "successRate": 0, "totalRequests": 0},
            "generatedAt": datetime.now().isoformat()
        }


# @api_router.get("/api/chatbot/analytics")
# def get_analytics(
#     userId: Optional[str] = Query(None),
#     fromDate: Optional[str] = Query(None),
#     toDate: Optional[str] = Query(None),
#     subjectId: Optional[str] = Query(None),
#     topicId: Optional[str] = Query(None)
# ):
#     """Get analytics with proper Pydantic model handling."""
#     try:
#         # Get all conversations from conversation_manager
#         all_conversations = conversation_manager.get_all_conversations()
        
#         # Convert Pydantic models to dictionaries
#         conversations_list = []
#         for conv in all_conversations:
#             # Convert Pydantic model to dict
#             if hasattr(conv, 'dict'):
#                 conv_dict = conv.dict()
#             elif hasattr(conv, 'model_dump'):
#                 conv_dict = conv.model_dump()
#             else:
#                 # Already a dict or convert with vars()
#                 conv_dict = conv if isinstance(conv, dict) else vars(conv)
            
#             conversations_list.append(conv_dict)
        
#         # Apply filters
#         filtered_conversations = conversations_list
        
#         if userId:
#             filtered_conversations = [c for c in filtered_conversations if c.get("userId") == userId]
        
#         if fromDate:
#             try:
#                 start_dt = datetime.fromisoformat(fromDate.replace('Z', '+00:00'))
#                 filtered_conversations = [
#                     c for c in filtered_conversations 
#                     if datetime.fromisoformat(c.get("createdAt", "")) >= start_dt
#                 ]
#             except:
#                 pass
        
#         if toDate:
#             try:
#                 end_dt = datetime.fromisoformat(toDate.replace('Z', '+00:00'))
#                 filtered_conversations = [
#                     c for c in filtered_conversations 
#                     if datetime.fromisoformat(c.get("createdAt", "")) <= end_dt
#                 ]
#             except:
#                 pass
        
#         if subjectId:
#             filtered_conversations = [c for c in filtered_conversations if c.get("subjectId") == subjectId]
        
#         if topicId:
#             filtered_conversations = [c for c in filtered_conversations if c.get("topicId") == topicId]
        
#         # Calculate analytics
#         total_queries = len(filtered_conversations)
        
#         # Calculate token usage (word count estimate)
#         internal_tokens = sum(
#             len(c.get("userMessage", "").split()) + len(c.get("aiResponse", "").split())
#             for c in filtered_conversations if c.get("mode") == "internal"
#         )
#         external_tokens = sum(
#             len(c.get("userMessage", "").split()) + len(c.get("aiResponse", "").split())
#             for c in filtered_conversations if c.get("mode") == "cloud"
#         )
        
#         # Estimate cost ($0.002 per 1K tokens)
#         cost_per_token = 0.000002
#         total_cost = (internal_tokens + external_tokens) * cost_per_token
        
#         # Calculate engagement metrics
#         unique_users = set(c.get("userId") for c in filtered_conversations if c.get("userId"))
#         response_times = [c.get("responseTime", 0) for c in filtered_conversations]
#         avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
#         # Analyze top subjects
#         subject_counts = {}
#         for c in filtered_conversations:
#             subj = c.get("subjectId", "Unknown")
#             subject_counts[subj] = subject_counts.get(subj, 0) + 1
        
#         top_subjects = [
#             {"subject": subj, "queries": count}
#             for subj, count in sorted(subject_counts.items(), key=lambda x: x, reverse=True)[:5]
#         ]
        
#         # Calculate success rate
#         success_count = len([c for c in filtered_conversations if not c.get("error")])
#         success_rate = (success_count / max(total_queries, 1)) * 100
        
#         # Build response
#         return {
#             "success": True,
#             "period": {
#                 "fromDate": fromDate,
#                 "toDate": toDate
#             },
#             "tokenUsage": {
#                 "internalMode": internal_tokens,
#                 "externalMode": external_tokens,
#                 "total": internal_tokens + external_tokens,
#                 "estimatedCost": round(total_cost, 4)
#             },
#             "userEngagement": {
#                 "totalQueries": total_queries,
#                 "uniqueUsers": len(unique_users),
#                 "avgResponseTime": round(avg_response_time, 2),
#                 "avgQueryLength": round(
#                     sum(len(c.get("userMessage", "").split()) for c in filtered_conversations) / max(total_queries, 1),
#                     2
#                 )
#             },
#             "topSubjects": top_subjects,
#             "systemPerformance": {
#                 "avgResponseTime": round(avg_response_time, 2),
#                 "successRate": round(success_rate, 2),
#                 "totalRequests": total_queries
#             },
#             "generatedAt": datetime.now().isoformat()
#         }
        
#     except Exception as e:
#         print(f"[ERROR] Analytics error: {str(e)}")
#         import traceback
#         traceback.print_exc()
        
#         # Return fallback response
#         return {
#             "success": True,
#             "period": {"fromDate": None, "toDate": None},
#             "tokenUsage": {"internalMode": 0, "externalMode": 0, "total": 0, "estimatedCost": 0},
#             "userEngagement": {"totalQueries": 0, "uniqueUsers": 0, "avgResponseTime": 0, "avgQueryLength": 0},
#             "topSubjects": [],
#             "systemPerformance": {"avgResponseTime": 0, "successRate": 0, "totalRequests": 0},
#             "generatedAt": datetime.now().isoformat()
#         }



@api_router.get("/chatbot/analytics/stats")
def get_analytics_stats():
    """Get basic analytics statistics."""
    try:
        all_conversations = conversation_manager.get_all_conversations()
        
        return {
            "ok": True,
            "totalConversations": len(all_conversations),
            "uniqueUsers": len(set(c.get("userId") for c in all_conversations if c.get("userId"))),
            "modes": {
                "internal": len([c for c in all_conversations if c.get("mode") == "internal"]),
                "cloud": len([c for c in all_conversations if c.get("mode") == "cloud"])
            },
            "avgResponseTime": round(sum(c.get("responseTime", 0) for c in all_conversations) / max(len(all_conversations), 1), 2),
            "generatedAt": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[ERROR] Stats error: {str(e)}")
        return {
            "ok": False,
            "error": str(e),
            "generatedAt": datetime.now().isoformat()
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
        # Validate required fields for PDF generation
        if request.contentType == "pdf" and request.mode == "internal":
            if not request.subjectName or not request.subjectName.strip():
                return GenerateContentResponse(
                    success=False,
                    contentId="",
                    userId=request.userId,
                    status="failed",
                    message="Subject Name is required for PDF generation in internal mode",
                    estimated_completion_time=None,
                    filePath=None,
                    fileName=None,
                    storageDirectory=None,
                    metadata=None
                )
            if not request.topicName or not request.topicName.strip():
                return GenerateContentResponse(
                    success=False,
                    contentId="",
                    userId=request.userId,
                    status="failed",
                    message="Topic Name is required for PDF generation in internal mode",
                    estimated_completion_time=None,
                    filePath=None,
                    fileName=None,
                    storageDirectory=None,
                    metadata=None
                )
        
        # Validate content type and config
        if request.contentType == "flashcard" and not request.contentConfig.get('flashcard'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Flashcard config is required for flashcard content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "quiz" and not request.contentConfig.get('quiz'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Quiz config is required for quiz content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "assessment" and not request.contentConfig.get('assessment'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Assessment config is required for assessment content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "video" and not request.contentConfig.get('video'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Video config is required for video content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "audio" and not request.contentConfig.get('audio'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Audio config is required for audio content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "compiler" and not request.contentConfig.get('compiler'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="Compiler config is required for compiler content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "pdf" and not request.contentConfig.get('pdf'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="PDF config is required for PDF content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
            )
        elif request.contentType == "ppt" and not request.contentConfig.get('ppt'):
            return GenerateContentResponse(
                success=False,
                contentId="",
                userId=request.userId,
                status="failed",
                message="PPT config is required for PPT content type",
                estimated_completion_time=None,
                filePath=None,
                fileName=None,
                storageDirectory=None,
                metadata=None
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
        
        # Extract file information from content metadata
        actual_file_name = content.metadata.get("actualFileName") if content.metadata else None
        actual_file_path = content.metadata.get("actualFilePath") if content.metadata else None
        storage_directory = content.metadata.get("storageDirectory") if content.metadata else None
        
        # Fallback to filePath if metadata not available
        if not actual_file_path and content.filePath:
            actual_file_path = content.filePath
        if not actual_file_name and actual_file_path:
            actual_file_name = os.path.basename(actual_file_path)
        if not storage_directory and actual_file_path:
            storage_directory = os.path.dirname(actual_file_path)
        
        return GenerateContentResponse(
            success=True,
            contentId=content.contentId,
            userId=request.userId,
            status=content.status,
            message=f"Content generation completed for {request.contentType}",
            estimated_completion_time=estimated_time,  # Use the alias name
            filePath=actual_file_path,
            fileName=actual_file_name,
            storageDirectory=storage_directory,
            metadata=content.metadata if content.metadata else {}
        )
        
    except Exception as e:
        import traceback
        print(f"[ERROR] Content generation failed: {str(e)}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return GenerateContentResponse(
            success=False,
            contentId="",
            userId=request.userId,
            status="failed",
            message=f"Error generating content: {str(e)}",
            estimated_completion_time=None,
            filePath=None,
            fileName=None,
            storageDirectory=None,
            metadata=None
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
        
        # Normalize file paths (convert Windows backslashes to forward slashes)
        from pathlib import Path
        for content_item in paginated_content:
            if content_item.filePath:
                # Convert to POSIX path format
                content_item.filePath = Path(content_item.filePath).as_posix()
        
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
            # Use the file path from content (which should be the actual media file)
            # If it's an audio file, check if it's the MP3/audio file or script file
            if content.contentType == "audio":
                # Check if the filePath is already the audio file (ends with .mp3, .wav, .ogg, etc.)
                audio_extensions = ['.mp3', '.wav', '.ogg', '.aac', '.flac']
                if any(content.filePath.lower().endswith(ext) for ext in audio_extensions):
                    media_file = content.filePath
                else:
                    # Fallback: try to find audio file in the same directory
                    storage_dir = os.path.dirname(content.filePath)
                    # Try different audio formats
                    for ext in audio_extensions:
                        potential_file = os.path.join(storage_dir, f"audio{ext}")
                        if os.path.exists(potential_file):
                            media_file = potential_file
                            break
                    else:
                        # If no audio file found, use the filePath (might be script file)
                        media_file = content.filePath
            else:  # video
                # For video, try to find video file
                storage_dir = os.path.dirname(content.filePath)
                video_file = os.path.join(storage_dir, "video.mp4")
                media_file = video_file if os.path.exists(video_file) else content.filePath
            
            # Determine media type based on file extension
            file_ext = os.path.splitext(media_file)[1].lower()
            media_type_map = {
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.ogg': 'audio/ogg',
                '.aac': 'audio/aac',
                '.flac': 'audio/flac',
                '.mp4': 'video/mp4'
            }
            media_type = media_type_map.get(file_ext, 'application/octet-stream')
            
            if os.path.exists(media_file):
                return FileResponse(
                    path=media_file,
                    filename=f"{contentId}{file_ext}",
                    media_type=media_type
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
