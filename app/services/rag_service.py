from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from typing import Any, Dict, List

from pypdf import filters

from app.repositories.scheme_repository import get_scheme_repository
from app.schemas.chat import Citation
from app.schemas.profile import UserProfile
from app.services.translation_service import get_translation_service
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
    "education": (
        ["education", "study", "school", "college", "academic"],
        """
        education assistance
        scholarship
        fee waiver
        study support
        academic assistance
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
    "employment": (
        ["employment", "job", "jobs", "work", "career", "unemployed"],
        """
        employment scheme
        skill development
        job training
        livelihood
        self employment
        """,
    ),
    "housing": (
        ["housing", "house", "home", "shelter", "awas"],
        """
        housing scheme
        pradhan mantri awas yojana
        home loan subsidy
        housing assistance
        """,
    ),
    "loan": (
        ["loan", "credit", "mudra", "subsidy"],
        """
        loan scheme
        mudra loan
        credit subsidy
        business loan
        """,
    ),
    "insurance": (
        ["insurance", "policy", "premium", "cover", "bima"],
        """
        insurance scheme
        life insurance
        accident insurance
        insurance cover
        """,
    ),
    "scholarship": (
        ["scholarship", "fellowship", "stipend"],
        """
        scholarship scheme
        pre matric scholarship
        post matric scholarship
        merit scholarship
        """,
    ),
    "disabled": (
        ["disabled", "disability", "divyang", "handicap"],
        """
        disability pension
        divyang scheme
        disability assistance
        accessibility support
        """,
    ),
}

ATTRIBUTE_CATEGORY_MAP: Dict[str, str] = {
    "farmer": "farmer",
    "student": "student",
    "business": "business",
}


def _contains_word(text: str, phrase: str) -> bool:
    """Whole-word/phrase match so 'farmer' doesn't match inside 'farmerish' etc."""
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return re.search(pattern, text) is not None


def _detect_categories(query: str) -> List[str]:
    q = clean_text(query).lower()
    detected: List[str] = []

    for category, (keywords, _expansion) in CATEGORY_EXPANSIONS.items():
        if any(_contains_word(q, kw) for kw in keywords):
            detected.append(category)

    return detected


def _extract_beneficiary_attributes(query: str) -> Dict[str, str]:
    q = clean_text(query).lower()
    attributes: Dict[str, str] = {}

    if any(_contains_word(q, w) for w in ("woman", "women", "female", "girl")):
        attributes["gender"] = "female"
    elif any(_contains_word(q, w) for w in ("man", "men", "male", "boy")):
        attributes["gender"] = "male"

    if any(_contains_word(q, w) for w in ("farmer", "kisan", "agriculture")):
        attributes["occupation"] = "farmer"
    elif any(_contains_word(q, w) for w in ("student", "scholar", "pupil")):
        attributes["occupation"] = "student"
    elif any(_contains_word(q, w) for w in ("business", "entrepreneur", "startup")):
        attributes["occupation"] = "business"
    elif any(_contains_word(q, w) for w in ("unemployed", "jobless", "job seeker")):
        attributes["occupation"] = "unemployed"

    if any(_contains_word(q, w) for w in ("disabled", "disability", "divyang", "handicap")):
        attributes["disability"] = "yes"

    if any(_contains_word(q, w) for w in ("widow", "widower")):
        attributes["marital_status"] = "widow"
    elif _contains_word(q, "married"):
        attributes["marital_status"] = "married"

    if any(
        _contains_word(q, w)
        for w in ("senior citizen", "old age", "elderly", "retired")
    ):
        attributes["age_group"] = "senior"
    elif any(_contains_word(q, w) for w in ("child", "children", "minor")):
        attributes["age_group"] = "minor"

    if any(
        _contains_word(q, w)
        for w in ("bpl", "below poverty line", "low income", "poor")
    ):
        attributes["income_group"] = "low"

    if any(
        _contains_word(q, w)
        for w in ("graduate", "post graduate", "phd", "engineering")
    ):
        attributes["education_level"] = "higher"
    elif any(_contains_word(q, w) for w in ("school", "primary", "secondary")):
        attributes["education_level"] = "school"

    return attributes


def _infer_category_from_attributes(attributes: Dict[str, str]) -> str | None:
    occupation = attributes.get("occupation")
    if occupation in ATTRIBUTE_CATEGORY_MAP:
        return ATTRIBUTE_CATEGORY_MAP[occupation]

    if attributes.get("disability") == "yes":
        return "disabled"

    if attributes.get("age_group") == "senior":
        return "pension"

    return None


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

    # State: item.get("state"), else metadata fallback, else not specified.
    state = item.get("state") or metadata.get("state") or NOT_SPECIFIED

    return (
        f"## {scheme_name}\n"
        f"Benefits: {benefits}\n"
        f"Eligibility: {eligibility}\n"
        f"How to Apply: {how_to_apply}\n"
        f"Website: {website}\n"
        f"State: {state}"
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
            formatted_state = " ".join(
                word.capitalize()
                for word in state.replace("-", " ").split()
            )

            where["$or"] = [
                {"state": formatted_state},
                {"state": "Central"},
            ]

        if filters:
            if filters.get("category"):
                where["category"] = filters["category"]

            if filters.get("level"):
                where["level"] = filters["level"]

        return where if where else None


    def _apply_ranking_boosts(
        self,
        combined: List[Dict[str, Any]],
        query: str,
        state: str | None,
    ) -> List[Dict[str, Any]]:

        query_words = [
            word for word in clean_text(query).lower().split() if len(word) > 2
        ]

        normalized_state = normalize_state(state) if state else None

        for row in combined:
            meta = row.get("metadata", {}) or {}
            boost = 0.0

            if normalized_state and meta.get("state") == normalized_state:
                boost += 1.0

            if str(meta.get("level", "")).lower() == "central":
                boost += 0.5

            text = (
                str(row.get("document", ""))
                + " "
                + str(meta.get("scheme_name", ""))
            ).lower()

            for word in query_words:
                if word in text:
                    boost += 0.20

            row["score"] = float(row.get("score", 0)) + boost

        return combined

    def retrieve(
        self,
        query: str,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:

        start_time = time.perf_counter()

        where = self.build_where_filter(state=state, filters=filters)

        detected_categories = _detect_categories(query)
        attributes = _extract_beneficiary_attributes(query)

        if filters and filters.get("category"):
            preferred_category = str(filters["category"])
        elif detected_categories:
            preferred_category = detected_categories[0]
        else:
            preferred_category = _infer_category_from_attributes(attributes)

        # search_keyword() already performs hybrid retrieval internally
        # (it does semantic candidate retrieval + keyword scoring), so we
        # avoid a separate search_semantic() call to reduce memory usage.
        try:
            keyword_results = get_scheme_repository().search_keyword(
                query,
                where=where,
                top_k=top_k,
                preferred_state=state,
                preferred_category=preferred_category,
            )
        except Exception as exc:
            logger.exception("Keyword (hybrid) search failed: %s", exc)
            keyword_results = []

        logger.info(
            "Detected categories=%s | attributes=%s | keyword_results=%d",
            detected_categories,
            attributes,
            len(keyword_results),
        )

        ranked = self._apply_ranking_boosts(keyword_results, query=query, state=state)

        aggregated = get_scheme_repository().aggregate_ranked(ranked)[:top_k]

        elapsed = time.perf_counter() - start_time
        logger.info(
            "retrieve() completed in %.3fs | %d schemes selected",
            elapsed,
            len(aggregated),
        )

        return aggregated

    async def answer(
        self,
        query: str,
        language: str = "en",
        user_profile: UserProfile | None = None,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        start_time = time.perf_counter()

        english_query = get_translation_service().translate_to_english(
            query,
            source_language=language,
        )

        detected_state = (
            state
            or (user_profile.state if user_profile else None)
            or detect_state(english_query)
        )

        if detected_state:
            detected_state = normalize_state(detected_state)

        enhanced_query = self.enhance_query(
            english_query,
            profile=user_profile,
            explicit_state=detected_state,
        )

        detected_categories = _detect_categories(enhanced_query)

        retrieved = self.retrieve(
            enhanced_query,
            state=detected_state,
            filters=filters,
            top_k=10,
        )

        logger.info(
            "Detected intent categories=%s | detected_state=%s | selected_schemes=%d",
            detected_categories,
            detected_state,
            len(retrieved),
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
        seen_scheme_ids: set[str] = set()

        for item in retrieved:

            scheme_id = str(item.get("scheme_id", ""))

            if scheme_id in seen_scheme_ids:
                continue

            seen_scheme_ids.add(scheme_id)

            scheme_name = (
                item.get("scheme_name")
                or item.get("title")
                or "Unknown Scheme"
            )

            citations.append(
                Citation(
                    scheme_id=scheme_id,
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

        answer = get_translation_service().translate_from_english(
            answer,
            target_language=language,
        )

        elapsed = time.perf_counter() - start_time
        logger.info("answer() completed in %.3fs", elapsed)

        return {
            "answer": answer,
            "detected_state": detected_state,
            "citations": citations,
            "results": retrieved,
        }


@lru_cache
def get_rag_service() -> RAGService:
    return RAGService()
