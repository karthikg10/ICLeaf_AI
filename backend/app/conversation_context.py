"""
Conversation context enhancement for chat continuity.

This module helps maintain conversation context by:
1. Detecting follow-up questions (vague, short, or containing references)
2. Expanding queries with relevant context from conversation history
3. Improving RAG/web search results for contextual queries
"""

import re
from typing import List, Optional, Tuple
from .models import SessionMessage


# Pronouns and reference words that indicate a follow-up question
FOLLOW_UP_INDICATORS = [
    r'\b(it|its|they|them|their|this|that|these|those)\b',
    r'\b(the topic|the subject|the concept|the thing)\b',
    r'\b(more|further|additional|also|another)\b',
    r'\b(explain|tell|describe|show|give)\s+(me|us)\s+(more|about|details)',
    r'\b(what about|how about|what else|tell me)\b',
    r'\b(pros|cons|advantages|disadvantages|benefits|drawbacks)\b',
    r'\b(example|examples|instance|instances)\b',
]


def is_follow_up_question(message: str, history: List[SessionMessage]) -> bool:
    """
    Detect if a message is likely a follow-up question that needs context.
    Only treats messages as follow-ups if they have explicit signals.
    
    Args:
        message: The current user message
        history: Previous conversation messages
        
    Returns:
        True if this appears to be a follow-up question
    """
    if not history or len(history) == 0:
        return False
    
    message_lower = message.lower().strip()
    
    # ONLY treat as follow-up if there are explicit signals
    
    # 1) Pronouns / reference words / "pros/cons/..." etc.
    for pattern in FOLLOW_UP_INDICATORS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            return True
    
    # 2) Vague starter phrases
    vague_starters = [
        "tell me", "explain", "what about", "how about",
        "what else", "give me", "show me", "describe"
    ]
    for starter in vague_starters:
        if message_lower.startswith(starter):
            return True
    
    # 3) Very short, but ONLY if they *look* like classic follow-ups
    # e.g. "more", "details", "examples", "its pros"
    if len(message_lower.split()) <= 3:
        if any(word in message_lower for word in ["more", "details", "examples", "pros", "cons"]):
            return True
    
    return False


def extract_key_terms_from_history(history: List[SessionMessage], max_terms: int = 5) -> List[str]:
    """
    Extract key terms from conversation history to help expand follow-up queries.
    
    Args:
        history: Previous conversation messages
        max_terms: Maximum number of key terms to extract
        
    Returns:
        List of key terms (words/phrases) from recent conversation
    """
    if not history:
        return []
    
    # Get recent user messages and assistant responses
    recent_messages = history[-6:]  # Last 6 messages (3 exchanges)
    
    # Collect all content
    all_text = " ".join([
        msg.content for msg in recent_messages 
        if msg.content and len(msg.content.strip()) > 0
    ])
    
    if not all_text:
        return []
    
    # Extract potential key terms (capitalized words, quoted phrases, or important nouns)
    # Simple heuristic: words that appear multiple times or are capitalized
    words = re.findall(r'\b[A-Z][a-z]+\b|\b[a-z]{4,}\b', all_text)
    
    # Count word frequencies
    word_counts = {}
    for word in words:
        word_lower = word.lower()
        if len(word_lower) >= 3:  # Ignore very short words
            word_counts[word_lower] = word_counts.get(word_lower, 0) + 1
    
    # Get most frequent terms
    sorted_terms = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    key_terms = [term for term, count in sorted_terms[:max_terms] if count >= 2]
    
    # Also look for quoted phrases or specific terms
    quoted = re.findall(r'"([^"]+)"', all_text)
    key_terms.extend(quoted[:2])  # Add up to 2 quoted phrases
    
    return key_terms[:max_terms]


def expand_query_with_context(
    current_message: str, 
    history: List[SessionMessage]
) -> Tuple[str, bool]:
    """
    Expand a query with context from conversation history if it's a follow-up.
    
    Args:
        current_message: The current user message
        history: Previous conversation messages
        
    Returns:
        Tuple of (expanded_query, was_expanded)
    """
    if not is_follow_up_question(current_message, history):
        return current_message, False
    
    # Extract key terms from history
    key_terms = extract_key_terms_from_history(history)
    
    if not key_terms:
        # If we can't extract terms, try to get the last user question
        user_messages = [msg for msg in history if msg.role == "user"]
        if user_messages:
            last_user_msg = user_messages[-1].content
            # Use the last user question as context
            expanded = f"{last_user_msg} {current_message}"
            return expanded, True
        return current_message, False
    
    # Build expanded query
    context_phrase = " ".join(key_terms[:3])  # Use top 3 key terms
    expanded = f"{context_phrase} {current_message}"
    
    return expanded.strip(), True


def get_conversation_summary(history: List[SessionMessage], max_length: int = 200) -> str:
    """
    Create a brief summary of the conversation for context.
    
    Args:
        history: Previous conversation messages
        max_length: Maximum length of summary
        
    Returns:
        Brief summary string
    """
    if not history:
        return ""
    
    # Get last few exchanges
    recent = history[-4:]  # Last 4 messages (2 exchanges)
    
    summary_parts = []
    for msg in recent:
        if msg.role == "user" and msg.content:
            # Truncate long messages
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            summary_parts.append(f"User asked: {content}")
        elif msg.role == "assistant" and msg.content:
            # Truncate long responses
            content = msg.content[:150] + "..." if len(msg.content) > 150 else msg.content
            summary_parts.append(f"Assistant: {content[:50]}...")
    
    summary = " | ".join(summary_parts)
    
    if len(summary) > max_length:
        summary = summary[:max_length] + "..."
    
    return summary

