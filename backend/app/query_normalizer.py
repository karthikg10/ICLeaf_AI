"""
Query normalization for handling singular/plural variations, synonyms, and word forms.

This module provides:
1. Stemming/lemmatization for root word matching
2. Singular/plural expansion
3. Synonym expansion
4. Query enhancement for better RAG retrieval
"""

import re
from typing import List, Set, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import NLTK for advanced processing, fallback to simple rules if not available
try:
    import nltk
    from nltk.stem import WordNetLemmatizer
    from nltk.corpus import wordnet as wn
    NLTK_AVAILABLE = True
    
    # Download required NLTK data if not present
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    
    try:
        nltk.data.find('corpora/wordnet')
    except LookupError:
        nltk.download('wordnet', quiet=True)
    
    try:
        nltk.data.find('taggers/averaged_perceptron_tagger')
    except LookupError:
        nltk.download('averaged_perceptron_tagger', quiet=True)
    
    lemmatizer = WordNetLemmatizer()
except ImportError:
    NLTK_AVAILABLE = False
    logger.warning("[QUERY_NORMALIZER] NLTK not available. Using simple rule-based normalization.")


# Common stop words to skip normalization
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "can", "could", "may", "might", "must", "shall", "what", "which", "who",
    "where", "when", "why", "how", "this", "that", "these", "those", "it",
    "its", "they", "them", "their", "there", "then", "than", "to", "from",
    "in", "on", "at", "by", "for", "with", "about", "into", "onto", "of",
    "and", "or", "but", "if", "as", "so", "not", "no", "yes", "all", "each",
    "every", "some", "any", "more", "most", "many", "much", "few", "little"
}

# Common plural/singular mappings for technical terms
PLURAL_SINGULAR_MAP: Dict[str, str] = {
    # Data structures
    "structures": "structure",
    "arrays": "array",
    "lists": "list",
    "trees": "tree",
    "graphs": "graph",
    "stacks": "stack",
    "queues": "queue",
    "heaps": "heap",
    "tables": "table",
    "sets": "set",
    "maps": "map",
    "dictionaries": "dictionary",
    
    # Algorithms
    "algorithms": "algorithm",
    "sorts": "sort",
    "searches": "search",
    "traversals": "traversal",
    "operations": "operation",
    "functions": "function",
    "methods": "method",
    "procedures": "procedure",
    
    # General tech terms
    "databases": "database",
    "servers": "server",
    "clients": "client",
    "nodes": "node",
    "edges": "edge",
    "vertices": "vertex",
    "elements": "element",
    "items": "item",
    "objects": "object",
    "classes": "class",
    "instances": "instance",
    "variables": "variable",
    "constants": "constant",
    "parameters": "parameter",
    "arguments": "argument",
    "exceptions": "exception",
    "errors": "error",
    "bugs": "bug",
    "features": "feature",
    "modules": "module",
    "packages": "package",
    "libraries": "library",
    "frameworks": "framework",
    "tools": "tool",
    "utilities": "utility",
    
    # Educational terms
    "concepts": "concept",
    "topics": "topic",
    "subjects": "subject",
    "lessons": "lesson",
    "chapters": "chapter",
    "sections": "section",
    "examples": "example",
    "exercises": "exercise",
    "problems": "problem",
    "solutions": "solution",
    "definitions": "definition",
    "explanations": "explanation",
    "descriptions": "description",
}

# Reverse mapping (singular -> plural)
SINGULAR_PLURAL_MAP: Dict[str, str] = {v: k for k, v in PLURAL_SINGULAR_MAP.items()}

# Common synonyms for technical terms
SYNONYM_MAP: Dict[str, List[str]] = {
    "data structure": ["data structures", "structure", "structures", "ds"],
    "algorithm": ["algorithms", "algo", "algos", "procedure", "method"],
    "array": ["arrays", "list", "lists"],
    "tree": ["trees", "hierarchy", "hierarchies"],
    "graph": ["graphs", "network", "networks"],
    "stack": ["stacks", "lifo", "last in first out"],
    "queue": ["queues", "fifo", "first in first out"],
    "database": ["databases", "db", "data store", "repository"],
    "function": ["functions", "method", "methods", "procedure", "routine"],
    "variable": ["variables", "var", "identifier"],
    "exception": ["exceptions", "error", "errors", "fault"],
    "class": ["classes", "type", "types", "object type"],
    "object": ["objects", "instance", "instances", "entity"],
    "module": ["modules", "package", "packages", "library", "libraries"],
    "api": ["apis", "interface", "interfaces", "endpoint", "endpoints"],
    "query": ["queries", "search", "searches", "request", "requests"],
    "node": ["nodes", "vertex", "vertices", "element"],
    "edge": ["edges", "link", "links", "connection", "connections"],
}


def _simple_plural_to_singular(word: str) -> Optional[str]:
    """Simple rule-based plural to singular conversion."""
    word_lower = word.lower()
    
    # Check explicit mapping first
    if word_lower in PLURAL_SINGULAR_MAP:
        return PLURAL_SINGULAR_MAP[word_lower]
    
    # Rule-based conversion
    if word_lower.endswith('ies'):
        return word_lower[:-3] + 'y'  # cities -> city
    elif word_lower.endswith('es') and len(word_lower) > 3:
        # Check if it's a valid plural (e.g., boxes, classes)
        if word_lower[-3] in 'sxz' or word_lower[-4:-2] in ['ch', 'sh']:
            return word_lower[:-2]  # boxes -> box, classes -> class
    elif word_lower.endswith('s') and len(word_lower) > 1:
        # Simple plural (cats -> cat)
        # But avoid words that end in 's' but aren't plural (as, is, etc.)
        if word_lower not in ['as', 'is', 'us', 'has', 'was', 'this', 'his']:
            return word_lower[:-1]
    
    return None


def _simple_singular_to_plural(word: str) -> Optional[str]:
    """Simple rule-based singular to plural conversion."""
    word_lower = word.lower()
    
    # Check explicit mapping first
    if word_lower in SINGULAR_PLURAL_MAP:
        return SINGULAR_PLURAL_MAP[word_lower]
    
    # Don't pluralize if already looks plural
    if word_lower.endswith('s') and word_lower not in STOP_WORDS:
        return None
    
    # Rule-based conversion
    if word_lower.endswith('y') and len(word_lower) > 1:
        # city -> cities
        return word_lower[:-1] + 'ies'
    elif word_lower.endswith(('s', 'x', 'z', 'ch', 'sh')):
        # box -> boxes, class -> classes
        return word_lower + 'es'
    elif word_lower.endswith('f'):
        # leaf -> leaves (simplified: just add 's')
        return word_lower + 's'
    else:
        # Simple case: add 's'
        return word_lower + 's'


def get_word_forms(word: str) -> Set[str]:
    """Get all word forms (singular, plural, stem) for a word."""
    forms: Set[str] = set()
    word_lower = word.lower().strip()
    
    if not word_lower:
        return forms
    
    forms.add(word_lower)  # Original
    
    # Get singular form
    singular = _simple_plural_to_singular(word_lower)
    if singular:
        forms.add(singular)
    
    # Get plural form
    plural = _simple_singular_to_plural(word_lower)
    if plural:
        forms.add(plural)
    
    # Use NLTK lemmatization if available
    if NLTK_AVAILABLE:
        try:
            # Try different POS tags for better lemmatization
            for pos in ['n', 'v', 'a']:  # noun, verb, adjective
                lemma = lemmatizer.lemmatize(word_lower, pos=pos)
                if lemma != word_lower:
                    forms.add(lemma)
                    # Also get plural of lemma
                    plural_lemma = _simple_singular_to_plural(lemma)
                    if plural_lemma:
                        forms.add(plural_lemma)
        except Exception as e:
            logger.debug(f"[QUERY_NORMALIZER] Error in lemmatization: {e}")
    
    return forms


def expand_with_synonyms(query: str) -> str:
    """Expand query with synonyms from the synonym map."""
    if not query or not query.strip():
        return query
    
    words = query.split()
    expanded_words: List[str] = []
    seen_terms: Set[str] = set()
    
    # Check for multi-word synonyms first
    query_lower = query.lower()
    for term, synonyms in SYNONYM_MAP.items():
        if term in query_lower and term not in seen_terms:
            # Add the term and its synonyms
            expanded_words.append(term)
            expanded_words.extend(synonyms[:2])  # Add first 2 synonyms
            seen_terms.add(term)
    
    # Then process individual words
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word.lower())
        
        # Check if this word has synonyms
        if clean_word in SYNONYM_MAP and clean_word not in seen_terms:
            expanded_words.append(word)
            expanded_words.extend(SYNONYM_MAP[clean_word][:2])
            seen_terms.add(clean_word)
        else:
            expanded_words.append(word)
    
    return " ".join(expanded_words)


def normalize_query(query: str, include_synonyms: bool = True) -> str:
    """
    Normalize a query by expanding word forms and synonyms.
    Only normalizes content words (skips stop words).
    
    Args:
        query: The original query text
        include_synonyms: Whether to include synonym expansion
        
    Returns:
        Normalized query with expanded word forms
    """
    if not query or not query.strip():
        return query
    
    # Split query into words
    words = query.split()
    normalized_parts: List[str] = []
    content_words: List[str] = []
    
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word.lower())
        
        # Skip stop words and very short words
        if clean_word in STOP_WORDS or len(clean_word) < 3:
            continue
        
        # Only normalize content words (nouns, technical terms, etc.)
        # Check if it's likely a content word (not a stop word, has length)
        if len(clean_word) >= 4 or clean_word in PLURAL_SINGULAR_MAP or clean_word in SINGULAR_PLURAL_MAP:
            content_words.append(clean_word)
            # Get all word forms (singular, plural, stem)
            word_forms = get_word_forms(word)
            # Filter out weird forms (like "structureses")
            valid_forms = [wf for wf in word_forms if len(wf) >= 3 and not wf.endswith('eses')]
            normalized_parts.extend(valid_forms[:3])  # Limit to 3 forms per word
    
    # Build normalized query: original + normalized content words
    if normalized_parts:
        normalized_query = query + " " + " ".join(normalized_parts)
    else:
        normalized_query = query
    
    # Add synonyms if requested (only for content words)
    if include_synonyms and content_words:
        synonym_expanded = expand_with_synonyms(" ".join(content_words))
        if synonym_expanded and synonym_expanded != " ".join(content_words):
            normalized_query += " " + synonym_expanded
    
    # Remove duplicates while preserving order
    seen = set()
    unique_parts = []
    for part in normalized_query.split():
        part_lower = part.lower()
        # Skip very short or weird forms
        if len(part_lower) >= 3 and part_lower not in seen and not part_lower.endswith('eses'):
            seen.add(part_lower)
            unique_parts.append(part)
    
    return " ".join(unique_parts)


def get_normalized_terms(query: str) -> Set[str]:
    """Get all normalized terms (word forms + synonyms) for a query."""
    terms: Set[str] = set()
    
    words = query.split()
    for word in words:
        clean_word = re.sub(r'[^\w]', '', word.lower())
        if clean_word:
            # Get word forms
            terms.update(get_word_forms(clean_word))
            
            # Get synonyms
            if clean_word in SYNONYM_MAP:
                terms.update(SYNONYM_MAP[clean_word])
    
    return terms

