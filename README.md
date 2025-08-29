# ICLeaF LMS Chatbot

An AI-powered assistant for **ICLeaF LMS** with two operating modes:

- **Cloud Mode** → uses web search, YouTube, and GitHub APIs to answer queries.  
- **Internal Mode (RAG)** → answers from your preloaded PDF/DOCX/PPTX/TXT documents.  

Also includes a **Content Generation module** to create **Summaries, Quizzes, or Lesson Plans**, downloadable as **PDF or PPTX**.

---

## 📂 Project Structure



---

## ⚙️ Prerequisites

- **Python 3.11+**
- **Node.js 18+ & npm**
- (macOS) Install system deps if using OCR fallback:
  ```bash
  brew install tesseract poppler


Environment Setup
Create a .env file in backend/:

OPENAI_API_KEY=your_openai_key_here
TAVILY_API_KEY=your_tavily_key_here      # optional (for web search in Cloud mode)
YOUTUBE_API_KEY=your_youtube_api_key     # optional
GITHUB_TOKEN=your_github_pat             # optional
DOCS_DIR=./seed_docs
REINDEX_ON_START=false
ALLOWED_ORIGINS=http://127.0.0.1:5173
OPENAI_MODEL=gpt-4o-mini


Running the Backend

~cd backend

~python3.11 -m venv .venv

~source .venv/bin/activate

~pip install -U pip

~pip install -r requirements.txt

# Start server
uvicorn app.main:app --reload --port 8000

Running the Frontend

~cd frontend

~npm install

~npm run dev


Features
1. Chat
Cloud Mode → fetches context from Tavily (web), YouTube, and GitHub.
Internal Mode → retrieves relevant chunks from your uploaded documents in backend/seed_docs/.
Sources are cited under each answer.

3. Internal Search & Topics
API endpoints for debugging:
GET /internal/search?q=term
GET /internal/topics (lists common terms/topics from docs)

5. Content Generation
Generate Summaries, Quizzes, Lesson Plans tailored for Learners / Trainers / Admins.
On-screen preview in the frontend
Download as PDF or PPTX with one click
Backend endpoints:
POST /generate → JSON content
POST /generate/pdf → download PDF
POST /generate/pptx → download PPTX

7. Index Management
POST /reindex → re-ingest docs ({"drop_db": true} to wipe old index)
GET /stats → show index size & docs_dir
📄 Adding Documents
Drop PDFs, DOCX, PPTX, or TXT files into backend/seed_docs/
Run POST /reindex (or restart with REINDEX_ON_START=true) to ingest.
Note: Image-only PDFs require OCR (optional via Tesseract).
🛠️ Development Notes
Backend stack: FastAPI + ChromaDB + OpenAI
Frontend stack: React + Vite (TypeScript)
Vector store: ChromaDB (local backend/data/chroma/)
PDF export: reportlab
PPTX export: python-pptx
✅ Quick Test
Start backend & frontend.
Visit http://127.0.0.1:5173
In Chat tab → ask: “What is a regex metacharacter?” (Internal mode)
In Generate tab → enter “Python Exception Handling”, choose Quiz, click Generate → then Download PDF/PPT.
