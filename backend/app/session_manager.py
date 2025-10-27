# backend/app/session_manager.py
from typing import Dict, List, Optional
from datetime import datetime
from .models import SessionMessage

# In-memory session storage (in production, use Redis or database)
_sessions: Dict[str, List[SessionMessage]] = {}

def append_history(sessionId: str, msg: SessionMessage) -> None:
    """Append a message to a session's history."""
    if sessionId not in _sessions:
        _sessions[sessionId] = []
    _sessions[sessionId].append(msg)

def get_history(sessionId: str, last: int = 10) -> List[SessionMessage]:
    """Get the last N messages for a given session."""
    if sessionId not in _sessions:
        return []
    return _sessions[sessionId][-last:] if last > 0 else _sessions[sessionId]

def clear_history(sessionId: str) -> None:
    """Clear the history for a session."""
    if sessionId in _sessions:
        _sessions[sessionId] = []

def get_all_sessions() -> Dict[str, List[SessionMessage]]:
    """Get all sessions (for debugging/admin purposes)."""
    return _sessions.copy()

def session_exists(sessionId: str) -> bool:
    """Check if a session exists."""
    return sessionId in _sessions

def filter_history_by_subject(sessionId: str, subjectId: str) -> List[SessionMessage]:
    """Get history filtered by subject ID."""
    if sessionId not in _sessions:
        return []
    return [msg for msg in _sessions[sessionId] if msg.subjectId == subjectId]

def filter_history_by_topic(sessionId: str, topicId: str) -> List[SessionMessage]:
    """Get history filtered by topic ID."""
    if sessionId not in _sessions:
        return []
    return [msg for msg in _sessions[sessionId] if msg.topicId == topicId]

def filter_history_by_document(sessionId: str, docName: str) -> List[SessionMessage]:
    """Get history filtered by document name."""
    if sessionId not in _sessions:
        return []
    return [msg for msg in _sessions[sessionId] if msg.docName == docName]
