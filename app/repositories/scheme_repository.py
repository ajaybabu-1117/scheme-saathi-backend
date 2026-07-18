from __future__ import annotations

import difflib
import logging
import os
from functools import lru_cache
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

import chromadb
from chromadb.config import Settings

from app.utils.text import clean_text

logger = logging.getLogger("scheme_repository")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "data/chroma")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "schemes")
EMBEDDING_MODEL_NAME: str = os.getenv(
    "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
)

FUZZY_THRESHOLD: float = 0.85
FUZZY_PARTIAL_MULTIPLIER: float = 0.5
FUZZY_MAX_WORDS_PER_FIELD: int = 60
FUZZY_MAX_LENGTH_DELTA: int = 2

SEMANTIC_CANDIDATE_POOL: int = int(os.getenv("SEMANTIC_CANDIDATE_POOL", "150"))

INTENT_BONUS: float = 6.0
CATEGORY_MATCH_BONUS: float = 3.0
STATE_MATCH_BONUS: float = 3.0
CENTRAL_LEVEL_BONUS: float = 1.0

FIELD_WEIGHTS: Dict[str, float] = {
    "scheme_name": 6.0,
    "keywords": 5.0,
    "benefits": 4.0,
    "eligibility": 3.0,
    "description": 2.0,
    "documents": 2.0,
    "category": 1.5,
    "state": 1.0,
    "website": 1.0,
}

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "health": [
        "health", "medical", "medicine", "doctor", "hospital", "clinic",
        "healthcare", "treatment", "disease", "insurance", "operation",
        "surgery", "family health", "ayushman", "wellness", "patient",
    ],
    "farmer": [
        "farmer", "farming", "agriculture", "crop", "cultivation", "kisan",
        "irrigation", "soil", "seed", "fertilizer", "farm", "farmland",
        "harvest", "agri",
    ],
    "education": [
        "education", "student", "school", "college", "university", "study",
        "academic", "hostel", "tuition", "exam", "learning",
    ],
    "women": [
        "women", "woman", "girl", "female", "widow", "mother", "mahila",
        "daughter", "pregnant", "maternity",
    ],
    "business": [
        "business", "startup", "enterprise", "entrepreneur", "msme", "udyam",
        "trade", "industry", "venture",
    ],
    "employment": [
        "employment", "job", "jobs", "career", "work", "salary", "skill",
        "livelihood", "placement", "training", "unemployment", "rojgar",
        "wages",
    ],
    "housing": [
        "housing", "house", "home", "property", "shelter", "awas",
        "residential", "dwelling",
    ],
    "pension": [
        "pension", "retirement", "old age", "senior citizen", "elderly",
    ],
    "disabled": [
        "disabled", "disability", "divyang", "special needs", "handicap",
        "specially abled", "differently abled",
    ],
    "student": [
        "student", "students", "pupil", "learner", "scholar",
    ],
    "scholarship": [
        "scholarship", "scholarships", "fellowship", "stipend", "grant",
    ],
    "loan": [
        "loan", "credit", "finance", "subsidy", "mudra", "funding", "borrow",
    ],
    "insurance": [
        "insurance", "policy", "premium", "cover", "bima", "claim",
    ],
}


class SchemeRepository:
    def __init__(self) -> None:
        try:
            self._client = chromadb.PersistentClient(
                path=CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=CHROMA_COLLECTION_NAME
            )
            logger.info("Persist Directory : %s", CHROMA_PERSIST_DIR)
            logger.info("Collection Name   : %s", CHROMA_COLLECTION_NAME)
            logger.info("Collection Count  : %s", self._collection.count())
            logger.info(
                "Connected to ChromaDB collection '%s' at '%s' (count=%s)",
                CHROMA_COLLECTION_NAME,
                CHROMA_PERSIST_DIR,
                self._safe_count(),
            )
        except Exception as exc:
            logger.exception("Failed to initialize ChromaDB client: %s", exc)
            raise

        self._embedder = None

        self._scheme_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._all_items_cache: Optional[List[Dict[str, Any]]] = None

    def _safe_count(self) -> int:
        try:
            return self._collection.count()
        except Exception:
            return -1

    @staticmethod
    def _build_state_where(
        state: Optional[str],
        extra_where: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        clauses: List[Dict[str, Any]] = []

        if state:
            normalized_state = " ".join(word.capitalize() for word in state.replace("-", " ").split())
            clauses.append(
                {
                    "$or": [
                        {"state": normalized_state},
                        
                        {"state": "central"},
                    ]
                }
            )
        
        if extra_where:
            for key, value in extra_where.items():
                if key == "state":
                    continue
                clauses.append({key: value})

        if not clauses:
            return None

        if len(clauses) == 1:
            return clauses[0]

        return {"$and": clauses}

    @staticmethod
    @lru_cache(maxsize=4096)
    def _normalize_text(value: str) -> str:
        return value.lower().strip().replace("-", " ").replace("_", " ")

    @lru_cache(maxsize=512)
    def _detect_intent(self, query: str) -> FrozenSet[str]:
        detected: List[str] = []
        lowered = clean_text(query).lower()

        for category, triggers in INTENT_KEYWORDS.items():
            for trigger in triggers:
                if trigger in lowered:
                    detected.append(category)
                    break

        return frozenset(detected)

    @staticmethod
    @lru_cache(maxsize=2048)
    def _tokenize(query: str) -> FrozenSet[str]:
        return frozenset(
            token
            for token in clean_text(query).lower().split()
            if len(token) > 2
        )

    @staticmethod
    def _field_text(metadata: Dict[str, Any], field: str) -> str:
        value = metadata.get(field, "")

        if isinstance(value, (list, tuple, set)):
            return clean_text(" ".join(str(v) for v in value)).lower()

        return clean_text(str(value)).lower()

    def _score_document(
        self,
        tokens: FrozenSet[str],
        document: str,
        metadata: Dict[str, Any],
    ) -> float:
        score = 0.0

        field_texts: Dict[str, str] = {
            field: self._field_text(metadata, field)
            for field in FIELD_WEIGHTS
        }
        if not field_texts.get("description"):
            field_texts["description"] = clean_text(document).lower()

        field_words_cache: Dict[str, List[str]] = {}

        for field, weight in FIELD_WEIGHTS.items():
            text = field_texts.get(field, "")
            if not text:
                continue

            unmatched_tokens: List[str] = []

            for token in tokens:
                if token in text:
                    score += weight
                else:
                    unmatched_tokens.append(token)

            if not unmatched_tokens:
                continue

            if field not in field_words_cache:
                field_words_cache[field] = text.split()[:FUZZY_MAX_WORDS_PER_FIELD]

            words = field_words_cache[field]

            for token in unmatched_tokens:
                for word in words:
                    if abs(len(word) - len(token)) > FUZZY_MAX_LENGTH_DELTA:
                        continue
                    ratio = difflib.SequenceMatcher(None, token, word).ratio()
                    if ratio > FUZZY_THRESHOLD:
                        score += weight * FUZZY_PARTIAL_MULTIPLIER
                        break

        return score

    def _compute_bonus(
        self,
        metadata: Dict[str, Any],
        detected_categories: FrozenSet[str],
        preferred_state: Optional[str],
        preferred_category: Optional[str],
    ) -> float:
        bonus = 0.0

        category_value = self._normalize_text(str(metadata.get("category", "")))
        state_value = self._normalize_text(str(metadata.get("state", "")))
        level_value = self._normalize_text(str(metadata.get("level", "")))

        if detected_categories and category_value in detected_categories:
            bonus += INTENT_BONUS

        if preferred_category and category_value == preferred_category:
            bonus += CATEGORY_MATCH_BONUS

        if preferred_state and state_value == preferred_state:
            bonus += STATE_MATCH_BONUS

        if level_value == "central":
            bonus += CENTRAL_LEVEL_BONUS

        return bonus

    @staticmethod
    def _normalize_distance(distance: Any) -> float:
        try:
            distance_value = float(distance)
        except (TypeError, ValueError):
            return 0.0

        if distance_value < 0:
            distance_value = 0.0

        return 1.0 / (1.0 + distance_value)

    @lru_cache(maxsize=256)
    def _embed_query(self, query: str) -> Tuple[float, ...]:
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                logger.exception("Failed to import SentenceTransformer: %s", exc)
                raise

            try:
                self._embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
                logger.info("Lazy-loaded embedding model '%s'", EMBEDDING_MODEL_NAME)
            except Exception as exc:
                logger.exception(
                    "Failed to load embedding model '%s': %s", EMBEDDING_MODEL_NAME, exc
                )
                raise

        vector = self._embedder.encode(query, normalize_embeddings=True)
        return tuple(float(x) for x in vector)

    def _get_semantic_candidates(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
        pool_size: int = SEMANTIC_CANDIDATE_POOL,
    ) -> List[Dict[str, Any]]:
        try:
            embedding = list(self._embed_query(query))
        except Exception as exc:
            logger.exception("Failed to embed query '%s': %s", query, exc)
            return []

        try:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=pool_size,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.exception(
                "Semantic candidate retrieval failed for query '%s': %s", query, exc
            )
            return []

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        candidates: List[Dict[str, Any]] = []

        for document, metadata, distance in zip(documents, metadatas, distances):
            try:
                candidates.append(
                    {
                        "document": document or "",
                        "metadata": metadata or {},
                        "semantic_score": self._normalize_distance(distance),
                    }
                )
            except Exception as exc:
                logger.warning("Skipping malformed candidate: %s", exc)
                continue

        return candidates

    def _get_all_items(
        self,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if where is None and self._all_items_cache is not None:
            return self._all_items_cache

        try:
            results = self._collection.get(
                where=where,
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            logger.exception("Failed to fetch items from ChromaDB: %s", exc)
            return []

        ids = results.get("ids", []) or []
        documents = results.get("documents", []) or []
        metadatas = results.get("metadatas", []) or []

        items: List[Dict[str, Any]] = []

        for idx, doc_id in enumerate(ids):
            try:
                document = documents[idx] if idx < len(documents) else ""
                metadata = metadatas[idx] if idx < len(metadatas) else {}
                items.append(
                    {
                        "id": doc_id,
                        "document": document or "",
                        "metadata": metadata or {},
                    }
                )
            except Exception as exc:
                logger.warning("Skipping malformed item at index %s: %s", idx, exc)
                continue

        if where is None:
            self._all_items_cache = items

        return items

    @lru_cache(maxsize=1)
    def _category_state_index(self) -> Dict[str, FrozenSet[str]]:
        try:
            result = self._collection.get(include=["metadatas"])
        except Exception as exc:
            logger.exception("Failed to build category/state index: %s", exc)
            return {"categories": frozenset(), "states": frozenset()}

        categories: List[str] = []
        states: List[str] = []

        for metadata in result.get("metadatas", []) or []:
            try:
                if metadata.get("category"):
                    categories.append(self._normalize_text(str(metadata["category"])))
                if metadata.get("state"):
                    states.append(self._normalize_text(str(metadata["state"])))
            except Exception as exc:
                logger.warning("Skipping malformed metadata during indexing: %s", exc)
                continue

        return {"categories": frozenset(categories), "states": frozenset(states)}

    def get_available_categories(self) -> List[str]:
        return sorted(self._category_state_index()["categories"])

    def get_available_states(self) -> List[str]:
        return sorted(self._category_state_index()["states"])

    def search_semantic(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            logger.warning("search_semantic called with empty query")
            return []

        try:
            embedding = list(self._embed_query(query))
        except Exception as exc:
            logger.exception("Failed to embed query '%s': %s", query, exc)
            return []

        try:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.exception("search_semantic failed for query '%s': %s", query, exc)
            return []

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        output: List[Dict[str, Any]] = []

        for document, metadata, distance in zip(documents, metadatas, distances):
            try:
                output.append(
                    {
                        "document": document or "",
                        "metadata": metadata or {},
                        "score": self._normalize_distance(distance),
                    }
                )
            except Exception as exc:
                logger.warning("Skipping malformed semantic result: %s", exc)
                continue

        return output

    def search_keyword(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        preferred_state: Optional[str] = None,
        preferred_category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            logger.warning("search_keyword called with empty query")
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        detected_categories = self._detect_intent(query)
        normalized_preferred_state = (
            self._normalize_text(preferred_state) if preferred_state else None
        )
        normalized_preferred_category = (
            self._normalize_text(preferred_category) if preferred_category else None
        )

        candidates = self._get_semantic_candidates(
            query=query, where=where, pool_size=SEMANTIC_CANDIDATE_POOL
        )

        if not candidates:
            logger.info(
                "Semantic candidate retrieval empty for query '%s', falling back to filtered scan",
                query,
            )
            candidates = self._get_all_items(where=where)
            for candidate in candidates:
                candidate["semantic_score"] = 0.0

        scored: List[Dict[str, Any]] = []

        for candidate in candidates:
            try:
                metadata = candidate.get("metadata", {}) or {}
                document = candidate.get("document", "") or ""
                semantic_score = float(candidate.get("semantic_score", 0.0))

                keyword_score = self._score_document(
                    tokens=tokens, document=document, metadata=metadata
                )
                bonus = self._compute_bonus(
                    metadata=metadata,
                    detected_categories=detected_categories,
                    preferred_state=normalized_preferred_state,
                    preferred_category=normalized_preferred_category,
                )

                final_score = semantic_score + keyword_score + bonus

                if final_score > 0:
                    scored.append(
                        {
                            "document": document,
                            "metadata": metadata,
                            "score": final_score,
                        }
                    )
            except Exception as exc:
                logger.warning("Skipping malformed record during keyword scoring: %s", exc)
                continue

        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:top_k]

    def search_by_state(
        self,
        query: str,
        state: str,
        top_k: int = 5,
        use_semantic: bool = False,
    ) -> List[Dict[str, Any]]:
        where = self._build_state_where(state=state, extra_where=None)

        if use_semantic:
            return self.search_semantic(query=query, where=where, top_k=top_k)

        return self.search_keyword(
            query=query, where=where, top_k=top_k, preferred_state=state
        )

    def search_by_category(
        self,
        query: str,
        category: str,
        top_k: int = 5,
        use_semantic: bool = False,
    ) -> List[Dict[str, Any]]:
        normalized_category = category.lower().strip().replace(" ", "-")
        where = {"category": normalized_category}

        if use_semantic:
            return self.search_semantic(query=query, where=where, top_k=top_k)

        return self.search_keyword(
            query=query, where=where, top_k=top_k, preferred_category=category
        )

    def get_scheme(self, scheme_id: str) -> Optional[Dict[str, Any]]:
        if not scheme_id:
            logger.warning("get_scheme called with empty scheme_id")
            return None

        if scheme_id in self._scheme_cache:
            cached = self._scheme_cache[scheme_id]
            return dict(cached) if cached else None

        try:
            result = self._collection.get(
                ids=[scheme_id],
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            logger.exception("get_scheme failed for id '%s': %s", scheme_id, exc)
            result = None

        metadata: Dict[str, Any] = {}
        document: str = ""

        if result and result.get("ids"):
            document = (result.get("documents") or [""])[0] or ""
            metadata = (result.get("metadatas") or [{}])[0] or {}
        else:
            try:
                fallback = self._collection.get(
                    where={"id": scheme_id},
                    include=["documents", "metadatas"],
                )
            except Exception as exc:
                logger.exception(
                    "get_scheme fallback lookup failed for id '%s': %s", scheme_id, exc
                )
                fallback = None

            if fallback and fallback.get("ids"):
                document = (fallback.get("documents") or [""])[0] or ""
                metadata = (fallback.get("metadatas") or [{}])[0] or {}

        if not metadata:
            logger.info("No scheme found for id '%s'", scheme_id)
            self._scheme_cache[scheme_id] = None
            return None

        payload = {
            "scheme_id": metadata.get("id", scheme_id),
            "scheme_name": metadata.get("scheme_name"),
            "description": metadata.get("description", document),
            "state": metadata.get("state"),
            "category": metadata.get("category"),
            "level": metadata.get("level"),
            "website": metadata.get("website"),
            "benefits": metadata.get("benefits"),
            "eligibility": metadata.get("eligibility"),
            "documents": metadata.get("documents"),
            "keywords": metadata.get("keywords"),
            "source_file": metadata.get("source_file"),
            "metadata": metadata,
        }

        self._scheme_cache[scheme_id] = payload
        return dict(payload)

    def aggregate_ranked(
        self,
        ranked_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not ranked_chunks:
            return []

        best: Dict[str, Dict[str, Any]] = {}

        for row in ranked_chunks:
            try:
                metadata = row.get("metadata", {}) or {}

                scheme_id = metadata.get("id") or metadata.get("scheme_id")
                if not scheme_id:
                    continue

                score = row.get("score", 0.0)
                document = row.get("document", "") or ""

                current = best.get(scheme_id)

                if current is not None and score <= current["score"]:
                    continue

                best[scheme_id] = {
                    "scheme_id": scheme_id,
                    "scheme_name": metadata.get("scheme_name"),
                    "state": metadata.get("state"),
                    "category": metadata.get("category"),
                    "level": metadata.get("level"),
                    "website": metadata.get("website"),
                    "score": score,
                    "snippet": document[:240],
                    "metadata": metadata,
                }
            except Exception as exc:
                logger.warning("Skipping malformed ranked chunk during aggregation: %s", exc)
                continue

        return sorted(best.values(), key=lambda item: item["score"], reverse=True)


@lru_cache
def get_scheme_repository() -> SchemeRepository:
    return SchemeRepository()
