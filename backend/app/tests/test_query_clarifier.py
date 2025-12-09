import os
import sys

import pytest

# Make backend package importable when running pytest from repo root.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.query_clarifier import evaluate_query_for_clarification


def test_clarifies_very_short_query():
    decision = evaluate_query_for_clarification("hi", history=None)
    assert decision.should_clarify is True
    assert decision.message


def test_clarifies_gibberish():
    decision = evaluate_query_for_clarification("asdf!!!!", history=None)
    assert decision.should_clarify is True
    assert decision.reason


def test_allows_normal_question():
    decision = evaluate_query_for_clarification("What is linear regression?", history=None)
    assert decision.should_clarify is False


def test_does_not_clarify_confirmation():
    """Test that confirmations like 'yes' don't trigger clarification after a clarification request."""
    from app.models import SessionMessage
    
    history = [
        SessionMessage(role="user", content="hi"),
        SessionMessage(role="assistant", content="Just to confirm: the question looks very short. Did you mean:\n- \"Hi\"?\nIf not, please rephrase with a bit more detail.")
    ]
    
    decision = evaluate_query_for_clarification("yes", history=history)
    assert decision.should_clarify is False


def test_does_not_clarify_follow_up():
    """Test that follow-up questions like 'explain more' don't trigger clarification."""
    from app.models import SessionMessage
    
    history = [
        SessionMessage(role="user", content="What is data science?"),
        SessionMessage(role="assistant", content="Data Science is...")
    ]
    
    decision = evaluate_query_for_clarification("explain more", history=history)
    assert decision.should_clarify is False

