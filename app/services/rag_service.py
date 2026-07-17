from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from app.repositories.scheme_repository import scheme_repository
from app.schemas.chat import Citation
from app.schemas.profile import UserProfile
from app.services.translation_service import translation_service
from app.utils.states import detect_state, normalize_state
from app.utils.text import clean_text

logger = logging.getLogger(__name__)

NOT_SPECIFIED = "Not specified in available data."

# Category -> (trigger keywords, expansion terms appended to the query)
CATEGORY_EXPANSIONS: Dict[str, tuple[list[str], str]] = {
    "farmer": (
        ["farmer", "agriculture", "crop", "farming"],
        """
        pm kisan
        ysr rythu bharosa
        kisan credit card
        crop insurance
        agriculture subsidy
        farmer welfare
        """,
    ),
    "student": (
        ["student", "scholarship", "education", "college"],
        """
        scholarship
        pre matric
        post matric
        merit scholarship
        education assistance
        student welfare
        """,
    ),
    "pension": (
        ["pension", "old age", "senior citizen", "retirement"],
        """
        old age pension
        widow pension
        retirement pension
        senior citizen pension
        social security
        """,
    ),
    "health": (
        ["health", "medical", "insurance", "hospital"],
        """
        health insurance
        ayushman bharat
        aarogyasri
        medical assistance
        health scheme
        """,
    ),
    "women": (
        ["woman", "women", "female", "girl"],
        """
        women empowerment
        girl child
        self employment
        financial assistance
        """,
    ),
    "business": (
        ["business", "startup", "entrepreneur"],
        """
        startup
        entrepreneur
        self employment
        loan subsidy
        business assistance
        """,
    ),
}


def _contains_word(text: str, phrase: str) -> bool:
    """Whole-word/phrase match so 'farmer' doesn't match inside 'farmerish' etc."""
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return re.search(pattern, text) is not None


def _build_scheme_section(item: Dict[str, Any]) -> str:
    """Build a deterministic Markdown section for a single retrieved scheme
    using ONLY fields present in the retrieved data. Never hallucinates."""

    metadata = item.get("metadata") or {}

    scheme_name = (
        item.get("scheme_name")
        or item.get("title")
        or "Unknown Scheme"
    )

    # Benefits: snippet first, then metadata["benefits"], else not specified.
    benefits = item.get("snippet") or metadata.get("benefits") or NOT_SPECIFIED

    # Eligibility: metadata["eligibility"], else not specified.
    eligibility = metadata.get("eligibility") or NOT_SPECIFIED

    # How to Apply: check known metadata keys in order, else not specified.
    how_to_apply = (
        metadata.get("how_to_apply")
        or metadata.get("application_process")
        or metadata.get("apply")
        or NOT_SPECIFIED
    )

    # Website: item.get("website"), else not specified.
    website = item.get("website") or NOT_SPECIFIED

    return (
        f"## {scheme_name}\n"
        f"Benefits: {benefits}\n"
        f"Eligibility: {eligibility}\n"
        f"How to Apply: {how_to_apply}\n"
        f"Website: {website}"
    )


class RAGService:

    def enhance_query(
        self,
        query: str,
        profile: UserProfile | None = None,
        explicit_state: str | None = None,
    ) -> str:

        q = clean_text(query).lower()

        state = explicit_state or (profile.state if profile else None)

        for _category, (keywords, expansion) in CATEGORY_EXPANSIONS.items():
            if any(_contains_word(q, kw) for kw in keywords):
                q += expansion

        if state:
            q += f" state:{state}"

        return q

    def build_where_filter(
        self,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:

        where: Dict[str, Any] = {}

        if state:
            where["state"] = normalize_state(state)

        if filters:
            for key in ("category", "level"):
                if filters.get(key):
                    where[key] = str(filters[key]).lower()

        return where or None

    def retrieve(
        self,
        query: str,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:

        where = self.build_where_filter(state=state, filters=filters)

        semantic = scheme_repository.search_semantic(
            query,
            where=where,
            top_k=top_k,
        )

        lexical = scheme_repository.search_keyword(
            query,
            where=where,
            top_k=top_k,
        )

        combined = semantic + lexical

        query_words = query.lower().split()

        for row in combined:

            meta = row.get("metadata", {})

            boost = 0.0

            if state and meta.get("state") == normalize_state(state):
                boost += 1.0

            text = (
                str(row.get("snippet", ""))
                + " "
                + str(row.get("scheme_name", ""))
            ).lower()

            for word in query_words:
                if word in text:
                    boost += 0.20

            row["score"] = float(row.get("score", 0)) + boost

        ranked = sorted(
            combined,
            key=lambda item: item.get("score", 0),
            reverse=True,
        )

        return scheme_repository.aggregate_ranked(ranked)[:top_k]

    async def answer(
        self,
        query: str,
        language: str = "en",
        user_profile: UserProfile | None = None,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        english_query = translation_service.translate_to_english(
            query,
            source_language=language,
        )

        detected_state = (
            state
            or detect_state(english_query)
            or (user_profile.state if user_profile else None)
        )

        if detected_state:
            detected_state = normalize_state(detected_state)

        enhanced_query = self.enhance_query(
            english_query,
            profile=user_profile,
            explicit_state=detected_state,
        )

        retrieved = self.retrieve(
            enhanced_query,
            state=detected_state,
            filters=filters,
            top_k=10,
        )

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Query: %s", english_query)
            logger.debug("Enhanced query: %s", enhanced_query)
            logger.debug("Detected state: %s", detected_state)
            logger.debug("Retrieved %d results", len(retrieved))
            for i, item in enumerate(retrieved, start=1):
                logger.debug(
                    "Result %d | scheme=%s state=%s website=%s",
                    i,
                    item.get("scheme_name"),
                    item.get("state"),
                    item.get("website"),
                )

        citations: List[Citation] = []

        for item in retrieved:

            scheme_name = (
                item.get("scheme_name")
                or item.get("title")
                or "Unknown Scheme"
            )

            citations.append(
                Citation(
                    scheme_id=str(item.get("scheme_id", "")),
                    scheme_name=str(scheme_name),
                    website=item.get("website"),
                    source_file=item.get("metadata", {}).get("source_file"),
                    state=item.get("state"),
                )
            )

        if not retrieved:
            answer = "No relevant schemes found in the available database."
        else:
            sections = ["# Recommended Schemes"]
            for item in retrieved:
                sections.append(_build_scheme_section(item))
            answer = "\n\n".join(sections)

        answer = translation_service.translate_from_english(
            answer,
            target_language=language,
        )

        return {
            "answer": answer,
            "detected_state": detected_state,
            "citations": citations,
            "results": retrieved,
        }


rag_service = RAGService()
