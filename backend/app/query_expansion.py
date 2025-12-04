# backend/app/query_expansion.py
"""
Query expansion utility for handling abbreviations in search queries.
Expands common abbreviations to include their full forms to improve RAG retrieval.
"""

import re
import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

# Common abbreviation mappings (case-insensitive)
ABBREVIATION_MAP: Dict[str, str] = {
    # Machine Learning & Data Science
    "ml": "Machine Learning",
    "ds": "Data Science",
    "ai": "Artificial Intelligence",
    "nlp": "Natural Language Processing",
    "cv": "Computer Vision",
    "dl": "Deep Learning",
    "nn": "Neural Network",
    "cnn": "Convolutional Neural Network",
    "rnn": "Recurrent Neural Network",
    "lstm": "Long Short-Term Memory",
    "gan": "Generative Adversarial Network",
    "svm": "Support Vector Machine",
    "knn": "K-Nearest Neighbors",
    "rf": "Random Forest",
    "gbm": "Gradient Boosting Machine",
    "xgboost": "XGBoost",
    "pca": "Principal Component Analysis",
    "svd": "Singular Value Decomposition",
    
    # General Tech
    "api": "Application Programming Interface",
    "ui": "User Interface",
    "ux": "User Experience",
    "db": "Database",
    "sql": "Structured Query Language",
    "nosql": "NoSQL",
    "rest": "Representational State Transfer",
    "json": "JavaScript Object Notation",
    "xml": "Extensible Markup Language",
    "html": "HyperText Markup Language",
    "css": "Cascading Style Sheets",
    "js": "JavaScript",
    "ts": "TypeScript",
    "http": "HyperText Transfer Protocol",
    "https": "HyperText Transfer Protocol Secure",
    "url": "Uniform Resource Locator",
    "uri": "Uniform Resource Identifier",
    "crud": "Create Read Update Delete",
    "orm": "Object-Relational Mapping",
    "mvc": "Model View Controller",
    "mvp": "Minimum Viable Product",
    
    # Cloud & DevOps
    "aws": "Amazon Web Services",
    "gcp": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "ci": "Continuous Integration",
    "cd": "Continuous Deployment",
    "cicd": "Continuous Integration Continuous Deployment",
    "devops": "Development Operations",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "docker": "Docker",
    
    # Statistics & Math
    "stat": "Statistics",
    "stats": "Statistics",
    "prob": "Probability",
    "dist": "Distribution",
    "var": "Variance",
    "std": "Standard Deviation",
    "corr": "Correlation",
    "reg": "Regression",
    "linreg": "Linear Regression",
    "logreg": "Logistic Regression",
}


def expand_query(query_text: str) -> str:
    """
    Expand abbreviations in a query to include their full forms.
    
    This function:
    1. Detects abbreviations in the query (as whole words)
    2. Expands them to include both the abbreviation and full form
    3. Preserves the original query structure
    
    Examples:
        "ML algorithms" -> "ML Machine Learning algorithms"
        "What is NLP?" -> "What is NLP Natural Language Processing?"
        "AI and ML" -> "AI Artificial Intelligence and ML Machine Learning"
    
    Args:
        query_text: The original query text
        
    Returns:
        Expanded query text with abbreviations and their full forms
    """
    if not query_text or not query_text.strip():
        return query_text
    
    # Normalize the query for processing
    expanded_parts = []
    words = query_text.split()
    
    # Track which abbreviations we've already expanded to avoid duplicates
    expanded_abbrevs: Set[str] = set()
    
    # Check if full forms are already present in the query (case-insensitive)
    query_lower = query_text.lower()
    
    for word in words:
        # Remove punctuation for matching (but preserve it)
        clean_word = re.sub(r'[^\w]', '', word.lower())
        
        # Check if this word is an abbreviation
        if clean_word in ABBREVIATION_MAP and clean_word not in expanded_abbrevs:
            full_form = ABBREVIATION_MAP[clean_word]
            # Check if the full form is already present in the query (case-insensitive)
            full_form_words = full_form.lower().split()
            full_form_present = all(fw in query_lower for fw in full_form_words)
            
            if not full_form_present:
                # Add both the original word and the full form
                expanded_parts.append(word)
                expanded_parts.append(full_form)
                expanded_abbrevs.add(clean_word)
            else:
                # Full form already present, just keep the original word
                expanded_parts.append(word)
                expanded_abbrevs.add(clean_word)  # Mark as processed to avoid re-checking
        else:
            # Keep the original word
            expanded_parts.append(word)
    
    # Join back with spaces
    expanded_query = " ".join(expanded_parts)
    
    # Log expansion if it happened
    if expanded_abbrevs:
        logger.debug(f"[QUERY_EXPANSION] Expanded abbreviations: {expanded_abbrevs} in query: '{query_text[:50]}...'")
    
    return expanded_query


def get_abbreviation_mappings() -> Dict[str, str]:
    """Get the current abbreviation mappings (for debugging/testing)."""
    return ABBREVIATION_MAP.copy()

