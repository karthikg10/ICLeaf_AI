# ICLeaF AI - Intelligent Content Learning Framework

A comprehensive AI-powered educational content generation and chatbot system built with FastAPI, OpenAI, and advanced RAG (Retrieval Augmented Generation) capabilities.

## 🚀 Features

### Core Capabilities
- **Intelligent Chatbot** with RAG and Cloud modes
- **Multi-format Content Generation** (PDF, PPT, Flashcards, Quizzes, Assessments, Videos, Audio, Code)
- **Knowledge Base Management** with embedding support
- **Conversation History and Analytics**
- **Session Management** with hierarchical organization
- **Real-time Status Tracking**

### Advanced Features
- **Rate Limiting** (10 requests/minute for chatbot)
- **Session-based Conversations** with metadata tracking
- **Content Generation Pipeline** with status monitoring
- **Analytics and Reporting** with comprehensive metrics
- **File Management** with organized storage
- **Error Handling** with detailed error reporting

## 🏗️ System Architecture

### API Structure
```
/api/
├── chatbot/           # Chatbot interaction and session management
├── content/           # Content generation and management
├── knowledge/         # Knowledge base embedding
├── internal/          # Internal search and documents
└── system/            # Health checks and statistics
```

### Core Components
- **RAG Store**: Chroma vector database for document storage
- **Conversation Manager**: Session and history management
- **Content Manager**: Content generation and file management
- **Embedding Service**: Text embedding with OpenAI
- **Session Manager**: User session tracking

## 📋 API Endpoints

### Chatbot Endpoints
- `POST /api/chatbot/query` - Main chatbot endpoint with session tracking
- `POST /api/chatbot/reset-session` - Reset session with scope filtering
- `GET /api/chatbot/history` - Get conversation history with filtering
- `GET /api/chatbot/analytics` - Get comprehensive analytics

### Content Generation
- `POST /api/content/generate` - Generate various content types
- `GET /api/content/list` - List user content with filtering
- `GET /api/content/download/{contentId}` - Download generated content
- `GET /api/content/{contentId}/status` - Check generation status

### Knowledge Base
- `POST /api/chatbot/knowledge/embed` - Embed knowledge content
- `POST /api/chatbot/knowledge/ingest-file` - Ingest single file
- `POST /api/chatbot/knowledge/ingest-dir` - Ingest directory

### System
- `GET /api/health` - Comprehensive system health check
- `GET /api/stats` - System statistics
- `GET /api/` - System overview and documentation

## 🎯 Content Types Supported

### Document Formats
- **PDF** - Structured document generation
- **PowerPoint** - Presentation creation

### Educational Content
- **Flashcards** - Front/back learning cards with difficulty levels
- **Quizzes** - Interactive quizzes with multiple question types
- **Assessments** - Comprehensive evaluations with scoring

### Media Content
- **Video** - Scripts and storyboards with quality settings
- **Audio** - Scripts and transcripts with format options
- **Code** - Multi-language code generation with tests

## 🔧 Configuration

### Environment Variables
```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini

# Cloud Search (Optional)
TAVILY_API_KEY=your_tavily_api_key
YOUTUBE_API_KEY=your_youtube_api_key
GITHUB_TOKEN=your_github_token

# CORS Configuration
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Document Directory
DOCS_DIR=./seed_docs
REINDEX_ON_START=false
```

### User Roles
- **Learner** - Basic access with simplified content
- **Trainer** - Advanced features with detailed content
- **Admin** - Full system access with administrative features

### Modes
- **Internal** - RAG-based responses using internal documents
- **Cloud** - Web search and external content integration

## 📊 Analytics and Monitoring

### Conversation Analytics
- Total conversations and users
- Response time metrics
- Mode usage statistics
- Subject/topic/document usage patterns
- Daily and hourly activity tracking

### Content Analytics
- Content generation statistics
- User engagement metrics
- Content type preferences
- Generation success rates

## 🗂️ Data Storage

### Storage Structure
```
/data/
├── content/
│   └── {userId}/
│       └── {contentId}/
│           ├── content.{ext}
│           └── metadata.json
├── chroma/
│   ├── chroma.sqlite3
│   └── {collection_id}/
└── conversations/ (in-memory)
```

### File Formats
- **JSON** - Structured content (flashcards, quizzes, assessments)
- **PDF** - Document content
- **PPTX** - Presentation content
- **TXT** - Script and transcript content
- **PY/JS/JAVA/CPP** - Code content

## 🚀 Getting Started

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Quick Start
1. **Health Check**: `GET /api/health`
2. **System Overview**: `GET /api/`
3. **Chatbot Query**: `POST /api/chatbot/query`
4. **Content Generation**: `POST /api/content/generate`

## 📈 Usage Examples

### Chatbot Interaction
```json
POST /api/chatbot/query
{
    "userId": "user123",
    "sessionId": "session456",
    "role": "Learner",
    "mode": "internal",
    "message": "Explain machine learning concepts",
    "subjectId": "computer_science",
    "topicId": "ai_ml"
}
```

### Content Generation
```json
POST /api/content/generate
{
    "userId": "user123",
    "role": "Trainer",
    "contentType": "flashcard",
    "prompt": "Create flashcards about Python programming",
    "contentConfig": {
        "flashcard": {
            "front": "What is Python?",
            "back": "Python is a high-level programming language",
            "difficulty": "easy"
        }
    }
}
```

### Knowledge Base Embedding
```json
POST /api/chatbot/knowledge/embed
{
    "subjectId": "computer_science",
    "topicId": "programming",
    "docName": "python_basics",
    "uploadedBy": "teacher123",
    "content": "Python is a versatile programming language..."
}
```

## 🔒 Security Features

- **Rate Limiting** - Prevents API abuse
- **Input Validation** - Comprehensive request validation
- **Error Handling** - Secure error reporting
- **User Isolation** - Content and session isolation
- **CORS Support** - Configurable cross-origin requests

## 📚 Dependencies

### Core Dependencies
- **FastAPI** - Web framework
- **OpenAI** - AI content generation
- **Pydantic** - Data validation
- **Chroma** - Vector database
- **Uvicorn** - ASGI server

### Content Processing
- **PyPDF** - PDF processing
- **python-docx** - Word document processing
- **python-pptx** - PowerPoint processing
- **Pillow** - Image processing
- **pytesseract** - OCR capabilities

### Additional Features
- **fastapi-limiter** - Rate limiting
- **redis** - Caching and session storage
- **httpx** - HTTP client
- **beautifulsoup4** - Web scraping

## 🎯 System Capabilities

### Intelligent Chatbot
- **RAG Mode** - Internal document-based responses
- **Cloud Mode** - Web search and external content
- **Session Management** - Persistent conversation history
- **Context Awareness** - Subject, topic, and document context

### Content Generation
- **Multi-format Support** - 8 different content types
- **Configuration-driven** - Flexible content customization
- **Status Tracking** - Real-time generation monitoring
- **File Management** - Organized content storage

### Knowledge Management
- **Document Embedding** - Vector-based document storage
- **Metadata Tracking** - Subject, topic, and document organization
- **Search Capabilities** - Advanced document search
- **Batch Processing** - Directory and file ingestion

## 🔄 System Flow

1. **User Interaction** → Chatbot endpoint
2. **Content Generation** → Content manager
3. **Knowledge Embedding** → Embedding service
4. **Session Tracking** → Session manager
5. **Analytics Collection** → Conversation manager
6. **File Storage** → Content manager
7. **Status Monitoring** → Real-time updates

## 📊 Monitoring and Analytics

### System Health
- Component status monitoring
- Resource usage tracking
- Error rate monitoring
- Performance metrics

### User Analytics
- Usage patterns and trends
- Content generation statistics
- Session and conversation metrics
- User engagement tracking

## 🎉 Conclusion

ICLeaF AI provides a comprehensive solution for educational content generation and intelligent chatbot interactions. With its modular architecture, extensive API coverage, and advanced AI capabilities, it serves as a complete platform for educational technology applications.

The system is designed for scalability, maintainability, and extensibility, making it suitable for various educational and content generation use cases.
