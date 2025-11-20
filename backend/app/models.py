# backend/app/models.py
from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator, Field, constr
from datetime import datetime

Role = Literal["student", "teacher", "admin"]
Mode = Literal["internal", "external"]

class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str = datetime.now().isoformat()
    subjectId: Optional[str] = None
    topicId: Optional[str] = None
    docName: Optional[str] = None

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    role: Role = "student"
    mode: Mode = "internal"
    message: constr(max_length=500)  # Enforce 500 char limit
    sessionId: str
    userId: str
    subjectId: Optional[str] = None
    topicId: Optional[str] = None
    docName: Optional[str] = None
    subjectName: Optional[str] = None
    topicName: Optional[str] = None
    docIds: List[str] = []  # For filtering by specific document IDs in internal mode
    history: List[SessionMessage] = []
    top_k: int = 4

    # Map "cloud" to "external" for backward compatibility
    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v == "cloud":
                v = "external"
        return v

class Source(BaseModel):
    title: str
    url: Optional[str] = None
    score: Optional[float] = None
    chunkId: Optional[str] = None
    docName: Optional[str] = None
    relevanceScore: Optional[float] = None

class ChatResponse(BaseModel):
    success: bool = True
    response: str = Field(alias="answer")  # Support both "answer" and "response"
    sources: List[Source] = []
    sessionId: str
    timestamp: str = datetime.now().isoformat()
    mode: Mode
    
    model_config = {"populate_by_name": True}  # Allow both field names



# ----- Content Generation -----
from typing import Literal

GenMode = Literal["cloud", "internal"]
GenKind = Literal["summary", "quiz", "lesson"]

class GenerateRequest(BaseModel):
    topic: str
    role: Role = "Learner"
    mode: GenMode = "internal"     # default to internal (RAG)
    kind: GenKind = "summary"
    top_k: int = 5                 # how many chunks / sources to retrieve (internal)
    max_context_blocks: int = 6    # cap total context blocks
    num_questions: int = 8         # only used if kind="quiz"

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v):
        if isinstance(v, str): v = v.strip().lower()
        return v

class GenerateResponse(BaseModel):
    ok: bool
    kind: GenKind
    topic: str
    content: str
    sources: List[Source] = []

# ----- Session Management -----
class ResetSessionRequest(BaseModel):
    sessionId: str
    userId: str
    subjectId: Optional[str] = None
    topicId: Optional[str] = None
    docName: Optional[str] = None
    resetScope: Optional[str] = "full"  # "full", "subject", "topic", "document"

class ResetSessionResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    sessionId: str
    userId: str
    message: str
    resetScope: str
    
    model_config = {"populate_by_name": True}

# ----- Pagination -----
class PaginationInfo(BaseModel):
    currentPage: int
    totalPages: int
    totalRecords: int
    recordsPerPage: int

# ----- Knowledge Base Embedding -----
class EmbedRequest(BaseModel):
    subjectId: str
    topicId: str
    docName: str
    uploadedBy: str
    content: Optional[str] = None  # For direct text content
    file_path: Optional[str] = None  # For file path

class EmbedResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    subjectId: str
    topicId: str
    docName: str
    uploadedBy: str
    chunks_processed: int
    embedding_model: str = "text-embedding-3-small"
    message: str
    docId: Optional[str] = None  # Unique document ID for filtering in content generation
    
    model_config = {"populate_by_name": True}

class IngestFileRequest(BaseModel):
    file_path: str
    subjectId: str
    topicId: str
    docName: str
    uploadedBy: str

class IngestDirRequest(BaseModel):
    dir_path: str
    subjectId: str
    topicId: str
    uploadedBy: str
    recursive: bool = True

# ----- Conversation History and Analytics -----
class Conversation(BaseModel):
    sessionId: str
    userId: str
    mode: Mode
    subjectId: Optional[str] = None
    topicId: Optional[str] = None
    docName: Optional[str] = None
    timestamp: str = datetime.now().isoformat()
    userMessage: str
    aiResponse: str
    sources: List[Source] = []
    responseTime: Optional[float] = None  # Response time in seconds
    tokenCount: Optional[int] = None  # Token count for the response

class ConversationHistory(BaseModel):
    conversations: List[Conversation]
    total_count: int
    sessionId: str
    userId: str

class HistoryRequest(BaseModel):
    sessionId: Optional[str] = None
    userId: Optional[str] = None
    subjectId: Optional[str] = None
    topicId: Optional[str] = None
    docName: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = 1
    limit: int = 20  # Default 20 as per spec

class HistoryResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    conversations: List[Conversation]
    pagination: PaginationInfo
    message: str
    
    model_config = {"populate_by_name": True}

# ----- Analytics Models -----
class AnalyticsMetrics(BaseModel):
    total_conversations: int
    total_users: int
    total_sessions: int
    average_response_time: float
    total_tokens_used: int
    mode_usage: dict  # {"cloud": count, "internal": count}
    subject_usage: dict  # {subjectId: count}
    topic_usage: dict  # {topicId: count}
    document_usage: dict  # {docName: count}
    daily_activity: List[dict]  # [{"date": "2024-01-01", "count": 10}]
    hourly_activity: List[dict]  # [{"hour": 14, "count": 5}]

class AnalyticsRequest(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    subjectId: Optional[str] = None
    topicId: Optional[str] = None
    userId: Optional[str] = None
    group_by: str = "day"  # "day", "hour", "subject", "topic", "user"

class AnalyticsResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    metrics: AnalyticsMetrics
    period: dict
    generated_at: datetime = datetime.now()
    
    model_config = {"populate_by_name": True}

# ----- Content Generation Models -----
ContentType = Literal["pdf", "ppt", "flashcard", "quiz", "assessment", "video", "audio", "compiler"]
ContentStatus = Literal["pending", "completed", "failed"]

class FlashcardConfig(BaseModel):
    front: str
    back: str
    difficulty: str = "medium"  # "easy", "medium", "hard"

class QuizConfig(BaseModel):
    num_questions: int = 5
    difficulty: str = "medium"
    question_types: List[str] = ["multiple_choice", "true_false"]  # "multiple_choice", "true_false", "short_answer"

class AssessmentConfig(BaseModel):
    duration_minutes: int = 30
    difficulty: str = "medium"
    question_types: List[str] = ["multiple_choice", "essay"]
    passing_score: int = 70

class VideoConfig(BaseModel):
    duration_seconds: int = 60  # 1 minute default
    quality: str = "720p"  # "480p", "720p", "1080p"
    include_subtitles: bool = True

class AudioConfig(BaseModel):
    duration_seconds: int = 300
    quality: str = "high"  # "low", "medium", "high"
    format: str = "mp3"  # "mp3", "wav", "ogg"
    voice_type: str = "female"  # "male", "female"
    target_audience: str = "general"  # "children", "students", "professionals", "general"

class CompilerConfig(BaseModel):
    language: str = "python"  # "python", "javascript", "java", "cpp"
    include_tests: bool = True
    difficulty: str = "medium"

class PDFConfig(BaseModel):
    num_pages: int = 5
    target_audience: str = "general"  # "children", "students", "professionals", "general"
    include_images: bool = True
    difficulty: str = "medium"  # "easy", "medium", "hard"

class PPTConfig(BaseModel):
    num_slides: int = 10
    target_audience: str = "general"  # "children", "students", "professionals", "general"
    include_animations: bool = True
    difficulty: str = "medium"  # "easy", "medium", "hard"

class ContentConfig(BaseModel):
    flashcard: Optional[FlashcardConfig] = None
    quiz: Optional[QuizConfig] = None
    assessment: Optional[AssessmentConfig] = None
    video: Optional[VideoConfig] = None
    audio: Optional[AudioConfig] = None
    compiler: Optional[CompilerConfig] = None
    pdf: Optional[PDFConfig] = None
    ppt: Optional[PPTConfig] = None


class GenerateContentRequest(BaseModel):
    userId: str
    role: str = "student"
    mode: str = "internal"
    contentType: str
    prompt: str
    contentConfig: dict = {}
    docIds: List[str] = []
    subjectName: Optional[str] = None
    topicName: Optional[str] = None
    
    # NEW FIELDS:
    customFileName: Optional[str] = None  # User-specified filename (without extension)
    customFilePath: Optional[str] = None  # User-specified directory path

# class GenerateContentRequest(BaseModel):
#     userId: str
#     role: Role = "Learner"
#     mode: Mode = "internal"
#     contentType: ContentType
#     prompt: str
#     docIds: Optional[List[str]] = None  # For internal mode
#     subjectName: Optional[str] = None  # For external mode
#     topicName: Optional[str] = None  # For external mode
#     contentConfig: dict

class GeneratedContent(BaseModel):
    contentId: str
    userId: str
    role: Role
    mode: Mode
    contentType: ContentType
    prompt: str
    status: ContentStatus
    createdAt: datetime = datetime.now()
    completedAt: Optional[datetime] = None
    filePath: Optional[str] = None
    downloadUrl: Optional[str] = None
    contentConfig: dict
    metadata: dict = {}
    error: Optional[str] = None

class GenerateContentResponse(BaseModel):
    success: bool = Field(alias="ok", default=True)  # Support both "ok" and "success"
    contentId: str
    userId: str
    status: ContentStatus
    message: str
    estimated_completion_time: Optional[int] = Field(default=None, alias="etaSeconds")  # seconds
    filePath: Optional[str] = None  # Actual storage file path
    fileName: Optional[str] = None  # Actual filename
    storageDirectory: Optional[str] = None  # Storage directory path
    metadata: Optional[dict] = None  # Additional metadata including actualFileName, actualFilePath, etc.
    
    model_config = {"populate_by_name": True}

class ContentListResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    contents: List[GeneratedContent] = Field(alias="content")  # Rename content to contents
    pagination: PaginationInfo
    userId: str
    
    model_config = {"populate_by_name": True}

class ContentDownloadResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    contentId: str
    filePath: str
    downloadUrl: str
    contentType: str
    fileSize: Optional[int] = None
    
    model_config = {"populate_by_name": True}

# Enhanced Analytics Models
class TokenUsage(BaseModel):
    internalMode: int
    externalMode: int
    totalCost: float

class UserEngagement(BaseModel):
    totalQueries: int
    avgSessionDuration: float
    messagesPerSession: float
    activeUsers: int

class TopSubject(BaseModel):
    subjectId: str
    queryCount: int
    percentage: float

class SystemPerformance(BaseModel):
    avgResponseTime: float
    successRate: float
    uptime: float

class EnhancedAnalyticsResponse(BaseModel):
    success: bool = Field(alias="ok")  # Support both "ok" and "success"
    period: dict
    tokenUsage: TokenUsage
    userEngagement: UserEngagement
    topSubjects: List[TopSubject]
    systemPerformance: SystemPerformance
    
    model_config = {"populate_by_name": True}

