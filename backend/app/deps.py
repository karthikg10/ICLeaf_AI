# backend/app/deps.py
import os
from dotenv import load_dotenv

# Load .env from backend/.env
load_dotenv()

# === LLM ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# === Cloud search (optional) ===
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# === CORS (for frontend later) ===
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
]
