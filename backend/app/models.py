# backend/app/models.py
from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator

Role = Literal["Learner", "Trainer", "Admin"]
Mode = Literal["cloud", "internal"]

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    role: Role = "Learner"
    mode: Mode = "cloud"
    message: str
    history: List[Message] = []
    top_k: int = 4

    # Normalize "mode" so "Internal", "INTERNAL", etc. become "internal"
    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
        return v

class Source(BaseModel):
    title: str
    url: Optional[str] = None
    score: Optional[float] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = []



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
