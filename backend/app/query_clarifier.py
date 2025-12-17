"""
Lightweight query clarification helpers used by chatbot flows.

Goals:
- Detect queries that are too short or look malformed.
- Offer a gentle clarification prompt with a best-guess reformulation.
- Skip clarification for follow-up questions and confirmations.
"""

from dataclasses import dataclass
from typing import Optional, List
import re
from .models import SessionMessage


@dataclass
class ClarificationDecision:
    should_clarify: bool
    reason: Optional[str] = None
    suggested_query: Optional[str] = None
    message: Optional[str] = None


def _normalize_query(text: str) -> str:
    """Basic cleanup to produce a readable suggestion."""
    cleaned = re.sub(r"\s+", " ", text or "").strip(" ?!.,;:").strip()
    # Avoid over-normalizing: keep original casing but ensure it starts nicely.
    if not cleaned:
        return ""
    # Capitalize first letter if the string is lowercase-ish.
    if cleaned.islower():
        cleaned = cleaned[:1].upper() + cleaned[1:]
    return cleaned


def _describe_reasons(reasons: List[str]) -> str:
    """Join human-friendly reasons."""
    if not reasons:
        return ""
    if len(reasons) == 1:
        return reasons[0]
    return ", ".join(reasons[:-1]) + f" and {reasons[-1]}"


def evaluate_query_for_clarification(
    query: str,
    history: Optional[List[SessionMessage]] = None,
    mode: str = "external",
    domain_hint: Optional[str] = None,
) -> ClarificationDecision:
    """
    Decide whether to ask the user for clarification.
    Heuristics only; no external dependencies.
    
    Args:
        query: The user's message
        history: Optional conversation history to check for context
        mode: "internal" or "external" - affects abbreviation disambiguation
        domain_hint: Optional hint (docName, subjectId, topicId) to help disambiguate in internal mode
    """
    text = (query or "").strip()
    if not text:
        return ClarificationDecision(
            should_clarify=True,
            reason="empty message",
            message="I didn't catch a question. Could you share what you want to ask?"
        )

    # FIRST: Check if this is a confirmation response (e.g., "yes" after a clarification)
    # Must be checked BEFORE any other logic to avoid "yes" triggering short-query checks
    if history and len(history) > 0:
        last_assistant_msg: Optional[str] = None
        for msg in reversed(history):
            if msg.role == "assistant":
                last_assistant_msg = msg.content or ""
                break
        
        # If last message was a clarification request, check if this is a confirmation
        if last_assistant_msg and ("Just to confirm" in last_assistant_msg or "Did you mean" in last_assistant_msg):
            confirmation_words = [
                "yes", "yeah", "yep", "yup",
                "ok", "okay", "sure", "correct",
                "right", "that's right", "exactly"
            ]
            text_lower_confirm = text.lower().strip()
            if text_lower_confirm in confirmation_words or text_lower_confirm in [w + "." for w in confirmation_words]:
                # Try to recover the suggested query from the previous clarification message
                suggested_from_last: Optional[str] = None

                # Case 1: generic short-query clarifier:
                # "Just to confirm: ... Did you mean:\n- \"Some cleaned query\"?"
                m1 = re.search(r'-\s*"([^"]+)"\?', last_assistant_msg)
                if m1:
                    suggested_from_last = m1.group(1)

                # Case 2: abbreviation clarifier:
                # "Did you mean 'machine learning'?\nIf not, please rephrase..."
                if suggested_from_last is None:
                    m2 = re.search(r"Did you mean '([^']+)'", last_assistant_msg)
                    if m2:
                        suggested_from_last = m2.group(1)

                return ClarificationDecision(
                    should_clarify=False,
                    reason="confirmation response",
                    suggested_query=suggested_from_last,
                    message=None,
                )

    # Explicit disambiguation for ambiguous abbreviations
    abbreviation_candidates = {
        "ds": ["data structures", "data science"],
        "ml": ["machine learning"],
        "dl": ["deep learning"],
        "cv": ["computer vision"],
        "nlp": ["natural language processing"],
        "ai": ["artificial intelligence"],
    }
    text_lower = text.lower()
    norm_lower = _normalize_query(text).lower()
    words = norm_lower.split()

    # Case 1: the entire text is just the abbreviation
    if text_lower in abbreviation_candidates and len(text_lower) <= 3:
        options = abbreviation_candidates[text_lower]
        
        # If we're in INTERNAL mode, try to filter options using the domain hint
        if mode == "internal" and domain_hint:
            dl = domain_hint.lower()
            # ALL words from the option must appear in the domain hint
            filtered = [
                opt for opt in options
                if all(word in dl for word in opt.split())
            ]
            if filtered:
                options = filtered
                # In internal mode with a clear match, AUTO-RESOLVE without asking
                if len(options) == 1:
                    return ClarificationDecision(
                        should_clarify=False,
                        reason="auto-resolved abbreviation",
                        suggested_query=options[0],
                        message=None,
                    )
        
        # External mode or multiple options still remaining - ask for clarification
        if len(options) == 1:
            suggestion = options[0]
            prompt = (
                f"Did you mean '{suggestion}'?\n"
                "If not, please rephrase with a bit more detail."
            )
            return ClarificationDecision(
                should_clarify=True,
                reason="ambiguous abbreviation",
                suggested_query=suggestion,
                message=prompt,
            )
        else:
            pretty_options = " or ".join(f"'{opt}'" for opt in options)
            prompt = (
                f"When you say '{text_lower}', do you mean {pretty_options}?\n"
                "If not, please rephrase with a bit more detail."
            )
            return ClarificationDecision(
                should_clarify=True,
                reason="ambiguous abbreviation",
                suggested_query=None,
                message=prompt,
            )

    # Case 2: last token is an abbreviation, e.g., "what is ds?"
    if words:
        last_token = words[-1]
        if last_token in abbreviation_candidates and len(last_token) <= 3:
            options = abbreviation_candidates[last_token]
            
            # If we're in INTERNAL mode, try to filter options using the domain hint
            if mode == "internal" and domain_hint:
                dl = domain_hint.lower()
                # ALL words from the option must appear in the domain hint
                filtered = [
                    opt for opt in options
                    if all(word in dl for word in opt.split())
                ]
                if filtered:
                    options = filtered
                    # In internal mode with a clear match, AUTO-RESOLVE without asking
                    if len(options) == 1:
                        expanded_query = " ".join(words[:-1] + [options[0]])
                        return ClarificationDecision(
                            should_clarify=False,
                            reason="auto-resolved abbreviation",
                            suggested_query=expanded_query,
                            message=None,
                        )
            
            # External mode or multiple options still remaining - ask for clarification
            if len(options) == 1:
                suggestion = options[0]
                expanded_query = " ".join(words[:-1] + [suggestion])
                prompt = (
                    f"When you say '{last_token}', did you mean '{suggestion}'?\n"
                    "If not, please rephrase with a bit more detail."
                )
                return ClarificationDecision(
                    should_clarify=True,
                    reason="ambiguous abbreviation",
                    suggested_query=expanded_query,
                    message=prompt,
                )
            else:
                pretty_options = " or ".join(f"'{opt}'" for opt in options)
                prompt = (
                    f"When you say '{last_token}', do you mean {pretty_options}?\n"
                    "If not, please rephrase with a bit more detail."
                )
                return ClarificationDecision(
                    should_clarify=True,
                    reason="ambiguous abbreviation",
                    suggested_query=None,
                    message=prompt,
                )

    # Check if this is a follow-up question (like "explain more", "tell me more", etc.)
    # These should be handled by conversation context, not clarification
    if history and len(history) > 0:
        follow_up_patterns = [
            r"explain\s+more",
            r"tell\s+me\s+more",
            r"tell\s+me\s+about",
            r"what\s+about",
            r"how\s+about",
            r"give\s+me\s+more",
            r"more\s+details",
            r"more\s+info",
            r"more\s+information",
        ]
        text_lower = text.lower()
        for pattern in follow_up_patterns:
            if re.search(pattern, text_lower):
                # This is a follow-up - let conversation context handle it
                return ClarificationDecision(should_clarify=False)

    words = text.split()
    reasons: List[str] = []

    # Heuristic: very short queries often need more context.
    # But be more lenient if there's conversation history (might be a follow-up)
    min_length = 8 if history and len(history) > 2 else 12
    min_words = 2 if history and len(history) > 2 else 3
    
    if len(text) < min_length or len(words) < min_words:
        reasons.append("the question looks very short")

    # Heuristic: unusual character mix (numbers/punctuation-heavy) -> might be malformed.
    alpha_count = sum(ch.isalpha() for ch in text)
    nonspace_len = len(text.replace(" ", ""))
    if nonspace_len > 0:
        alpha_ratio = alpha_count / nonspace_len
        if alpha_ratio < 0.45:
            reasons.append("it seems to have many non-word characters")

    # Heuristic: repeated characters (e.g., "hhhhhhh") or gibberish blocks.
    if re.search(r"(.)\1{4,}", text.lower()):
        reasons.append("it looks like accidental keypresses or gibberish")

    # If no reasons, proceed normally.
    if not reasons:
        return ClarificationDecision(should_clarify=False)

    suggested = _normalize_query(text)
    reason_text = _describe_reasons(reasons)

    if suggested and suggested != text:
        prompt = (
            f"Just to confirm: {reason_text}. Did you mean:\n"
            f"- \"{suggested}\"?\n"
            "If not, please rephrase with a bit more detail."
        )
    else:
        prompt = (
            f"Just to confirm: {reason_text}. "
            "Can you share a bit more detail about what you need?"
        )

    return ClarificationDecision(
        should_clarify=True,
        reason=reason_text,
        suggested_query=suggested if suggested != text else None,
        message=prompt,
    )


