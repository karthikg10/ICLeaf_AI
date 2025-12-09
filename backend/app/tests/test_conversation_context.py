"""
Tests for conversation context enhancement.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.conversation_context import (
    is_follow_up_question,
    expand_query_with_context,
    get_conversation_summary
)
from app.models import SessionMessage


def test_is_follow_up_question():
    """Test follow-up question detection."""
    history = [
        SessionMessage(role="user", content="What is Data Science?"),
        SessionMessage(role="assistant", content="Data Science is...")
    ]
    
    # Should detect follow-up
    assert is_follow_up_question("Tell its pros", history) is True
    assert is_follow_up_question("explain more", history) is True
    assert is_follow_up_question("what about it", history) is True
    assert is_follow_up_question("hi", history) is True  # Very short
    
    # Should not detect as follow-up
    assert is_follow_up_question("What is Machine Learning?", history) is False
    
    # No history should return False
    assert is_follow_up_question("Tell its pros", []) is False


def test_expand_query_with_context():
    """Test query expansion with context."""
    history = [
        SessionMessage(role="user", content="What is Data Science?"),
        SessionMessage(role="assistant", content="Data Science is the field that combines statistics, programming, and domain expertise...")
    ]
    
    # Follow-up question should be expanded
    expanded, was_expanded = expand_query_with_context("Tell its pros", history)
    assert was_expanded is True
    assert len(expanded) > len("Tell its pros")
    
    # Non-follow-up should not be expanded
    expanded2, was_expanded2 = expand_query_with_context("What is Machine Learning?", history)
    assert was_expanded2 is False
    assert expanded2 == "What is Machine Learning?"


def test_get_conversation_summary():
    """Test conversation summary generation."""
    history = [
        SessionMessage(role="user", content="What is Data Science?"),
        SessionMessage(role="assistant", content="Data Science is a field..."),
        SessionMessage(role="user", content="Tell me more"),
        SessionMessage(role="assistant", content="It involves...")
    ]
    
    summary = get_conversation_summary(history)
    assert len(summary) > 0
    assert "Data Science" in summary or "data science" in summary.lower()


if __name__ == "__main__":
    test_is_follow_up_question()
    test_expand_query_with_context()
    test_get_conversation_summary()
    print("All tests passed!")

