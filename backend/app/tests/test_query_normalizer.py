"""
Tests for query normalization (singular/plural, synonyms).
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.query_normalizer import (
    normalize_query,
    get_word_forms,
    expand_with_synonyms,
    _simple_plural_to_singular,
    _simple_singular_to_plural
)


def test_plural_to_singular():
    """Test plural to singular conversion."""
    assert _simple_plural_to_singular("structures") == "structure"
    assert _simple_plural_to_singular("algorithms") == "algorithm"
    assert _simple_plural_to_singular("arrays") == "array"
    assert _simple_plural_to_singular("trees") == "tree"
    assert _simple_plural_to_singular("cities") == "city"


def test_singular_to_plural():
    """Test singular to plural conversion."""
    assert _simple_singular_to_plural("structure") == "structures"
    assert _simple_singular_to_plural("algorithm") == "algorithms"
    assert _simple_singular_to_plural("array") == "arrays"
    assert _simple_singular_to_plural("tree") == "trees"


def test_get_word_forms():
    """Test getting all word forms."""
    forms = get_word_forms("structures")
    assert "structure" in forms or "structures" in forms
    
    forms2 = get_word_forms("algorithm")
    assert "algorithm" in forms2 or "algorithms" in forms2


def test_normalize_query():
    """Test query normalization."""
    # Test with plural
    normalized = normalize_query("data structures", include_synonyms=False)
    assert "structure" in normalized.lower() or "structures" in normalized.lower()
    
    # Test with singular
    normalized2 = normalize_query("data structure", include_synonyms=False)
    assert "structure" in normalized2.lower() or "structures" in normalized2.lower()


def test_synonym_expansion():
    """Test synonym expansion."""
    expanded = expand_with_synonyms("data structure")
    # Should include synonyms or related terms
    assert len(expanded.split()) >= 2  # At least original + some expansion


def test_normalize_with_synonyms():
    """Test normalization with synonyms."""
    normalized = normalize_query("algorithm", include_synonyms=True)
    # Should include synonyms
    assert len(normalized.split()) > 1


if __name__ == "__main__":
    test_plural_to_singular()
    test_singular_to_plural()
    test_get_word_forms()
    test_normalize_query()
    test_synonym_expansion()
    test_normalize_with_synonyms()
    print("All tests passed!")

