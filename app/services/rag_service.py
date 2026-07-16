from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Set, Tuple

from app.repositories.scheme_repository import scheme_repository
from app.schemas.chat import Citation
from app.schemas.profile import UserProfile
from app.services.llm_service import llm_service
from app.services.translation_service import translation_service
from app.utils.states import detect_state, normalize_state
from app.utils.text import clean_text

# ---------------------------------------------------------------------------
# Logging (replaces scattered print() calls with proper, level-based logging)
# ---------------------------------------------------------------------------
logger = logging.getLogger("scheme_saathi.rag")
if not logger.handlers:
    # Avoids duplicate handlers if the module gets reloaded (e.g. by uvicorn --reload)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Category knowledge base
# ---------------------------------------------------------------------------
# Each category maps to a broad set of synonyms / related terms, including
# common English phrasing, Hindi/Telugu transliterations, and scheme-specific
# jargon. This single source of truth is used for BOTH query expansion and
# category-match scoring, so the two never drift out of sync.
#
# Adding a new domain (e.g. "housing") is now a one-line addition here rather
# than a new `if` block scattered through enhance_query().
CATEGORY_SYNONYMS: Dict[str, List[str]] = {
    "farmer": [
        "farmer", "farmers", "agriculture", "agricultural", "crop", "crops",
        "farming", "kisan", "krishi", "rythu", "annadata", "cultivator",
        "pm kisan", "pmkisan", "ysr rythu bharosa", "rythu bharosa",
        "kisan credit card", "kcc", "crop insurance", "fasal bima",
        "agriculture subsidy", "farmer welfare", "irrigation", "seed subsidy",
    ],
    "student": [
        "student", "students", "scholarship", "scholarships", "education",
        "college", "school", "vidya", "vidyarthi", "chaduvu", "study",
        "tuition", "fee reimbursement", "pre matric", "post matric",
        "merit scholarship", "education assistance", "student welfare",
        "hostel", "books", "exam fee",
    ],
    "pension": [
        "pension", "pensions", "old age", "senior citizen", "senior citizens",
        "retirement", "vృద్ధాప్య", "vridha", "old age pension",
        "widow pension", "disability pension", "retirement pension",
        "senior citizen pension", "social security", "vృద్ధులు",
    ],
    "health": [
        "health", "medical", "insurance", "hospital", "healthcare",
        "arogya", "aarogya", "swasthya", "treatment", "surgery", "illness",
        "health insurance", "ayushman bharat", "aarogyasri", "arogyasri",
        "medical assistance", "health scheme", "medicine", "dialysis",
        "cancer treatment",
    ],
    "women": [
        "woman", "women", "female", "girl", "girls", "mahila", "stri",
        "matru", "women empowerment", "girl child", "self employment",
        "financial assistance", "widow", "maternity", "pregnancy benefit",
        "sukanya", "beti",
    ],
    "business": [
        "business", "startup", "entrepreneur", "udyog", "vyapar", "vyapara",
        "self employed", "startup india", "entrepreneur", "loan subsidy",
        "business assistance", "mudra loan", "small business", "msme",
        "self help group", "shg",
    ],
    "housing": [
        "house", "housing", "home", "shelter", "awas", "gruha", "illu",
        "pradhan mantri awas yojana", "pmay", "rural housing",
        "urban housing", "house construction", "house subsidy",
        "housing scheme", "own house",
    ],
    "employment": [
        "job", "jobs", "employment", "unemployment", "rozgar", "ugyogam",
        "skill development", "training", "livelihood", "wage", "nrega",
        "mgnrega", "employment scheme",
    ],
    "disability": [
        "disability", "disabled", "divyang", "handicap", "pwd",
        "differently abled", "disability pension", "disability scheme",
    ],
}

# Words that hint a scheme is nationwide/central rather than tied to a
# particular state. Used to keep central schemes visible even when a user's
# query (or profile) is scoped to a specific state.
CENTRAL_STATE_MARKERS = {"", "central", "national", "all", "india", "pan india", "union"}


def _normalize_token(token: str) -> str:
    return token.strip().lower()


def _fuzzy_hit(token: str, keyword: str, threshold: float = 0.84) -> bool:
    """
    Typo-tolerant, partial match between a query token and a known keyword.
    Cheap substring check first (fast path), fall back to a similarity ratio
    so small typos ("farmr", "insurence", "pention") still match.
    """
    if not token or not keyword:
        return False
    if token in keyword or keyword in token:
        return True
    # Only worth the fuzzy ratio calc for reasonably close-length tokens,
    # otherwise "a" would fuzzy-match everything.
    if abs(len(token) - len(keyword)) > 4:
        return False
    return SequenceMatcher(None, token, keyword).ratio() >= threshold


def detect_categories(query: str) -> Set[str]:
    """
    Returns the set of categories a free-text query matches, using both
    substring and fuzzy (typo-tolerant) matching against CATEGORY_SYNONYMS.
    """
    q = _normalize_token(query)
    tokens = [t for t in q.replace(",", " ").split() if t]

    matched: Set[str] = set()
    for category, keywords in CATEGORY_SYNONYMS.items():
        for keyword in keywords:
            # Multi-word keywords ("pm kisan") -> substring match against full query
            if " " in keyword:
                if keyword in q:
                    matched.add(category)
                    break
                continue
            # Single-word keywords -> per-token fuzzy match (typo tolerance)
            if any(_fuzzy_hit(tok, keyword) for tok in tokens):
                matched.add(category)
                break

    return matched


class RAGService:

    # ------------------------------------------------------------------
    # 1. Query expansion — now driven by CATEGORY_SYNONYMS + fuzzy matching
    #    instead of a fixed set of exact-substring `if` blocks. This means:
    #      - typos ("farmr scheme") still expand correctly
    #      - Hindi/Telugu transliterations are recognised
    #      - adding a new domain only requires editing CATEGORY_SYNONYMS
    # ------------------------------------------------------------------
    def enhance_query(
        self,
        query: str,
        profile: UserProfile | None = None,
        explicit_state: str | None = None,
    ) -> str:

        q = clean_text(query).lower()

        state = explicit_state or (
            profile.state if profile else None
        )

        try:
            matched_categories = detect_categories(q)
        except Exception:  # never let query expansion crash the request
            logger.exception("Category detection failed, continuing without expansion")
            matched_categories = set()

        expansion_terms: List[str] = []
        for category in matched_categories:
            expansion_terms.extend(CATEGORY_SYNONYMS.get(category, []))

        if expansion_terms:
            # Dedup while preserving order, keep it readable for lexical search
            seen = set()
            deduped = []
            for term in expansion_terms:
                if term not in seen:
                    seen.add(term)
                    deduped.append(term)
            q += "\n" + "\n".join(deduped)

        if state:
            q += f" state:{state}"

        return q

    # ------------------------------------------------------------------
    # 2. Where-filter — IMPORTANT FIX:
    #    Previously `state` was baked into a hard equality filter, which
    #    meant any query resolved to a state would ONLY ever see that
    #    state's schemes and would silently exclude central schemes
    #    (which typically have state = None/"central"). That also made the
    #    state-based `boost` logic in retrieve() pointless, since every
    #    row already matched.
    #
    #    Fix: state is no longer part of the hard `where` filter by default.
    #    It's used purely as a ranking boost in retrieve(), so users get
    #    BOTH their state's schemes AND relevant central schemes, ranked
    #    sensibly. A caller can still force a hard state filter by passing
    #    filters={"strict_state": True} for backward-compatible edge cases.
    # ------------------------------------------------------------------
    def build_where_filter(
        self,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:

        where: Dict[str, Any] = {}

        strict_state = bool(filters and filters.get("strict_state"))
        if strict_state and state:
            where["state"] = normalize_state(state)

        if filters:
            for key in ("category", "level"):
                if filters.get(key):
                    where[key] = str(filters[key]).lower()

        return where or None

    # ------------------------------------------------------------------
    # 3. Retrieve — smarter ranking:
    #    - fetches a wider candidate pool before ranking (better recall)
    #    - fuzzy token matching instead of exact substring (typo tolerance)
    #    - category-match boost (so "crop subsidy" ranks farmer schemes higher)
    #    - explicit "central scheme" boost so they aren't drowned out when a
    #      state is detected
    #    - wrapped in try/except per data source so one backend hiccup
    #      (e.g. semantic search down) doesn't fail the whole request
    # ------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:

        where = self.build_where_filter(
            state=state,
            filters=filters,
        )

        # Pull a larger candidate pool than top_k so ranking/boosting has
        # enough material to work with, especially once we mix in central
        # schemes alongside state schemes.
        fetch_k = max(top_k * 3, 20)

        semantic: List[Dict[str, Any]] = []
        lexical: List[Dict[str, Any]] = []

        try:
            semantic = scheme_repository.search_semantic(
                query,
                where=where,
                top_k=fetch_k,
            )
        except Exception:
            logger.exception("Semantic search failed, continuing with lexical results only")

        try:
            lexical = scheme_repository.search_keyword(
                query,
                where=where,
                top_k=fetch_k,
            )
        except Exception:
            logger.exception("Keyword search failed, continuing with semantic results only")

        combined = semantic + lexical

        if not combined:
            logger.warning("No results from semantic or keyword search for query: %s", query)
            return []

        normalized_state = normalize_state(state) if state else None
        query_tokens = [t for t in query.lower().split() if t]

        try:
            matched_categories = detect_categories(query)
        except Exception:
            logger.exception("Category detection failed during ranking")
            matched_categories = set()

        for row in combined:

            meta = row.get("metadata", {}) or {}
            row_state = (row.get("state") or meta.get("state") or "").strip().lower()

            boost = 0.0

            # Exact state match — strongest signal a user's own state scheme
            # is relevant.
            if normalized_state and row_state == normalized_state:
                boost += 2.0

            # Central / nationwide schemes remain visible and reasonably
            # ranked even when a state was detected, instead of being
            # crowded out entirely.
            if row_state in CENTRAL_STATE_MARKERS:
                boost += 1.0

            # Fuzzy text relevance instead of brittle exact substring checks,
            # so small typos in the query still find the right scheme.
            text = (
                str(row.get("snippet", ""))
                + " "
                + str(row.get("scheme_name", ""))
                + " "
                + str(meta.get("category", ""))
            ).lower()
            text_tokens = text.split()

            for word in query_tokens:
                if word in text:
                    boost += 0.20
                elif any(_fuzzy_hit(word, tok) for tok in text_tokens):
                    boost += 0.10

            # Category-match boost: if the user's query resolved to e.g.
            # "farmer" and this row is tagged (or reads) as a farmer scheme,
            # push it up.
            row_category = str(meta.get("category") or row.get("category") or "").lower()
            if matched_categories and any(cat in row_category or row_category in cat for cat in matched_categories):
                boost += 0.75

            row["score"] = float(row.get("score", 0)) + boost

        ranked = sorted(
            combined,
            key=lambda item: item.get("score", 0),
            reverse=True,
        )

        try:
            return scheme_repository.aggregate_ranked(ranked)[:top_k]
        except Exception:
            logger.exception("aggregate_ranked failed, falling back to raw ranked list")
            # Graceful fallback: de-dup by scheme_id manually so the API
            # still returns something useful instead of erroring out.
            seen_ids = set()
            fallback: List[Dict[str, Any]] = []
            for item in ranked:
                sid = item.get("scheme_id") or item.get("scheme_name")
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                fallback.append(item)
                if len(fallback) >= top_k:
                    break
            return fallback

    # ------------------------------------------------------------------
    # 4. Answer — same response shape / API contract, but:
    #    - print() -> logger.debug/info
    #    - translation and LLM calls wrapped in try/except with sensible
    #      fallbacks so a translation or LLM outage degrades gracefully
    #      instead of throwing a 500
    # ------------------------------------------------------------------
    async def answer(
        self,
        query: str,
        language: str = "en",
        user_profile: UserProfile | None = None,
        state: str | None = None,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        try:
            english_query = translation_service.translate_to_english(
                query,
                source_language=language,
            )
        except Exception:
            logger.exception("translate_to_english failed, falling back to raw query")
            english_query = query

        try:
            detected_state = (
                state
                or detect_state(english_query)
                or (user_profile.state if user_profile else None)
            )
            if detected_state:
                detected_state = normalize_state(detected_state)
        except Exception:
            logger.exception("State detection failed, continuing without a detected state")
            detected_state = state

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

        logger.info(
            "query=%r enhanced=%r state=%s results=%d",
            english_query, enhanced_query, detected_state, len(retrieved),
        )
        for i, item in enumerate(retrieved):
            logger.debug(
                "Result %d: scheme=%s state=%s website=%s",
                i + 1, item.get("scheme_name"), item.get("state"), item.get("website"),
            )

        context_lines = []
        citations: List[Citation] = []

        for item in retrieved:

            scheme_name = (
                item.get("scheme_name")
                or item.get("title")
                or "Unknown Scheme"
            )

            context_lines.append(
                f"""
Scheme: {scheme_name}
State: {item.get('state')}
Category: {item.get('category')}
Level: {item.get('level')}
Website: {item.get('website')}
Details: {item.get('snippet')}
"""
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

        context = "\n".join(context_lines)

        # If nothing was retrieved, skip the LLM call entirely — cheaper,
        # faster, and avoids the model second-guessing rule #6 below.
        if not retrieved:
            fallback_answer = "No relevant schemes found in the available database."
            try:
                fallback_answer = translation_service.translate_from_english(
                    fallback_answer,
                    target_language=language,
                )
            except Exception:
                logger.exception("translate_from_english failed for empty-result fallback")

            return {
                "answer": fallback_answer,
                "detected_state": detected_state,
                "citations": citations,
                "results": retrieved,
            }

        system_prompt = """
You are SCHEME SAATHI, an AI assistant for Indian Government Schemes.

IMPORTANT RULES:
1. Use ONLY schemes present in RETRIEVED SCHEMES.
2. NEVER invent scheme names.
3. NEVER invent websites.
4. NEVER invent eligibility criteria.
5. If information is missing, say:
   "Not specified in available data."
6. If no schemes are retrieved, say:
   "No relevant schemes found in the available database."
7. Use the exact scheme name and website from the retrieved data.

- Scheme Name
- Benefits
- Eligibility
- Application Process
- Official Website (if available)

5. Answer in simple language.
6. If multiple schemes exist, rank them by relevance.
7. If eligibility or application process is not explicitly mentioned, write "Not specified in available data".
8. Include website links whenever they are available.
9. Focus on schemes matching the user's state and category, but ALSO include
   relevant central/nationwide schemes even if the user's state was not
   mentioned or detected.

Output format:

# Recommended Schemes

## Scheme Name
Benefits:
Eligibility:
How to Apply:
Website:

## Scheme Name
Benefits:
Eligibility:
How to Apply:
Website:
"""

        user_prompt = f"""
USER QUESTION:
{english_query}

RETRIEVED SCHEMES:
{context}

The retrieved schemes ARE the answer.

Instructions:
1. Recommend the most relevant schemes first.
2. Summarize benefits clearly.
3. Mention eligibility if available.
4. Explain how to apply.
5. Include official website links.
6. Do NOT say that information is unavailable if schemes are present.
7. If multiple schemes are found, rank them by relevance.
- Use ONLY the schemes shown below.
- Do NOT generate additional schemes.
- Do NOT generate websites that are not in the retrieved context.
- If information is missing, write:
  "Not specified in available data."
"""

        try:
            answer = await llm_service.generate(
                system_prompt,
                user_prompt,
            )
        except Exception:
            logger.exception("LLM generation failed")
            answer = (
                "Sorry, I couldn't generate a response right now. "
                "Please try again in a moment."
            )

        try:
            answer = translation_service.translate_from_english(
                answer,
                target_language=language,
            )
        except Exception:
            logger.exception("translate_from_english failed, returning English answer")

        return {
            "answer": answer,
            "detected_state": detected_state,
            "citations": citations,
            "results": retrieved,
        }


rag_service = RAGService()