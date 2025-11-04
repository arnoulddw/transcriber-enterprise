# app/utils/title_utils.py
# Helpers for cleaning and normalizing LLM-generated transcription titles.

import re
from typing import Set

TITLE_MAX_WORDS = 5
TITLE_WORD_LIMIT_STOPWORDS: Set[str] = {
    'a', 'an', 'the', 'and', 'or', 'but', 'for', 'nor', 'on', 'in', 'at', 'to', 'of', 'with', 'without',
    'from', 'by', 'about', 'into', 'over', 'after', 'before', 'between', 'under', 'around', 'during',
    'de', 'la', 'el', 'los', 'las', 'por', 'del', 'y', 'en', 'un', 'una', 'unos', 'unas', 'para', 'con', 'al'
}


def clean_generated_title(raw_title: str) -> str:
    """Reduce whitespace and strip wrapping punctuation from raw LLM output."""
    if not raw_title:
        return ""
    cleaned = re.sub(r"\s+", " ", raw_title)
    cleaned = cleaned.strip()
    cleaned = cleaned.strip("\"'`")
    return cleaned.strip()


def enforce_word_limit(
    title: str,
    max_words: int = TITLE_MAX_WORDS,
    *,
    stopwords: Set[str] = TITLE_WORD_LIMIT_STOPWORDS,
) -> str:
    """
    Ensure a title respects the max word limit by pruning filler words or truncating.
    This keeps auto-title generation resilient even when the LLM slightly exceeds the limit.
    """
    if not title:
        return ""

    words = [word.strip(".,;:!?\"'()[]{}") for word in title.split()]

    if len(words) <= max_words:
        return " ".join(filter(None, words))

    filtered_words = [word for word in words if word and word.lower() not in stopwords]
    if filtered_words and len(filtered_words) <= max_words:
        return " ".join(filtered_words)

    fallback_words = filtered_words if filtered_words else words
    return " ".join(word for word in fallback_words[:max_words] if word)
