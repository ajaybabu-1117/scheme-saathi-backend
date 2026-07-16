from rapidfuzz import fuzz

from app.utils.search_config import (
    SEARCH_SYNONYMS,
    CATEGORY_KEYWORDS,
)


def expand_query(query: str) -> str:
    expanded = query.lower()

    for key, words in SEARCH_SYNONYMS.items():
        if key in expanded:
            expanded += " " + " ".join(words)

    return expanded


def detect_category(query: str):
    query = query.lower()

    for category, words in (
        CATEGORY_KEYWORDS.items()
    ):
        for word in words:
            if word in query:
                return category

    return None


def fuzzy_match(
    token: str,
    text: str,
) -> bool:
    return (
        fuzz.partial_ratio(
            token.lower(),
            text.lower(),
        )
        >= 80
    )