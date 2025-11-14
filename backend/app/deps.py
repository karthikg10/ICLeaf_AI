# backend/app/deps.py
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Determine the backend directory (parent of this file's directory)
BACKEND_DIR = Path(__file__).parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# Load .env file with explicit path
# Try multiple locations: backend/.env, then current directory
env_loaded = False
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)
    env_loaded = True
    print(f"[CONFIG] Loaded .env from: {ENV_FILE}")
else:
    # Try to find .env in current directory or parent directories
    env_path = find_dotenv()
    if env_path:
        load_dotenv(env_path, override=True)
        env_loaded = True
        print(f"[CONFIG] Loaded .env from: {env_path}")
    else:
        # Try loading from backend directory explicitly
        load_dotenv(dotenv_path=ENV_FILE, override=False)
        print(f"[CONFIG] Warning: .env file not found at {ENV_FILE} or in search path")
        print(f"[CONFIG] Attempting to load from environment variables...")

def _get_env(key: str, default: str = None, required: bool = False) -> str:
    """Get environment variable with trimming and validation."""
    value = os.getenv(key, default)
    if value is not None:
        value = value.strip()  # Remove leading/trailing whitespace
        # Remove quotes if present
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        value = value.strip()
    
    if required and not value:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            f"Please check your .env file at {ENV_FILE} or set it as an environment variable."
        )
    
    return value

def _validate_openai_api_key(api_key: str) -> bool:
    """Validate OpenAI API key format."""
    if not api_key:
        return False
    # OpenAI API keys start with "sk-" and are typically 51 characters long
    # But they can vary, so we just check for "sk-" prefix
    if not api_key.startswith("sk-"):
        return False
    # Minimum length check (sk- prefix + at least some characters)
    if len(api_key) < 10:
        return False
    return True

# === LLM ===
_openai_api_key_raw = _get_env("OPENAI_API_KEY", required=False)
OPENAI_API_KEY = None

if _openai_api_key_raw:
    # Validate and clean the API key
    if _validate_openai_api_key(_openai_api_key_raw):
        OPENAI_API_KEY = _openai_api_key_raw
        print(f"[CONFIG] OpenAI API key loaded successfully (length: {len(OPENAI_API_KEY)})")
    else:
        print(f"[CONFIG] ERROR: Invalid OpenAI API key format!")
        print(f"[CONFIG] API key should start with 'sk-' and be a valid OpenAI key.")
        print(f"[CONFIG] Current key (first 10 chars): {_openai_api_key_raw[:10]}...")
        print(f"[CONFIG] Please check your .env file at {ENV_FILE}")
        OPENAI_API_KEY = None
else:
    print(f"[CONFIG] WARNING: OPENAI_API_KEY not found in environment!")
    print(f"[CONFIG] Please set OPENAI_API_KEY in your .env file at {ENV_FILE}")
    print(f"[CONFIG] Format: OPENAI_API_KEY=sk-your-key-here")
    OPENAI_API_KEY = None

OPENAI_MODEL = _get_env("OPENAI_MODEL", "gpt-4o-mini")

# === Cloud search (optional) ===
TAVILY_API_KEY = _get_env("TAVILY_API_KEY", "")
YOUTUBE_API_KEY = _get_env("YOUTUBE_API_KEY", "")
GITHUB_TOKEN = _get_env("GITHUB_TOKEN", "")

# === CORS (for frontend later) ===
_allowed_origins_raw = _get_env("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
ALLOWED_ORIGINS = [
    o.strip() for o in _allowed_origins_raw.split(",") if o.strip()
]

# Print configuration status
print(f"[CONFIG] Configuration loaded:")
print(f"[CONFIG]   - OpenAI API Key: {'✓ Set' if OPENAI_API_KEY else '✗ Not set'}")
print(f"[CONFIG]   - OpenAI Model: {OPENAI_MODEL}")
print(f"[CONFIG]   - Tavily API Key: {'✓ Set' if TAVILY_API_KEY else '✗ Not set (optional)'}")
print(f"[CONFIG]   - YouTube API Key: {'✓ Set' if YOUTUBE_API_KEY else '✗ Not set (optional)'}")
print(f"[CONFIG]   - GitHub Token: {'✓ Set' if GITHUB_TOKEN else '✗ Not set (optional)'}")
print(f"[CONFIG]   - Allowed Origins: {ALLOWED_ORIGINS}")
