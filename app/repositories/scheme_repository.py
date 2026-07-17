from __future__ import annotations

import difflib
import logging
import os
from typing import Any, Dict, List, Optional, Set

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

CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "chroma_db")
CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "government_schemes")

FUZZY_THRESHOLD: float = 0.85
FUZZY_PARTIAL_MULTIPLIER: float = 0.5

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
    "health": ["health", "medical", "hospital", "treatment", "ayushman", "disease", "doctor"],
    "farmer": ["farmer", "farming", "agriculture", "crop", "kisan", "irrigation", "farmland"],
    "education": ["education", "school", "college", "university", "study", "academic"],
    "women": ["women", "woman", "girl", "mahila", "female", "widow"],
    "business": ["business", "startup", "enterprise", "entrepreneur", "msme", "udyam"],
    "employment": ["employment", "job", "jobs", "career", "unemployment", "work", "rojgar"],
    "housing": ["housing", "house", "home", "awas", "shelter", "residential"],
    "pension": ["pension", "retirement", "old age", "senior citizen"],
    "disabled": ["disabled", "disability", "handicap", "divyang", "specially abled"],
    "student": ["student", "students", "pupil", "learner"],
    "scholarship": ["scholarship", "scholarships", "fellowship", "stipend"],
    "loan": ["loan", "credit", "finance", "subsidy", "mudra"],
    "insurance": ["insurance", "bima", "cover", "policy", "premium"],
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
            logger.info(
                "Connected to ChromaDB collection '%s' at '%s' (count=%s)",
                CHROMA_COLLECTION_NAME,
                CHROMA_PERSIST_DIR,
                self._safe_count(),
            )
        except Exception as exc:
            logger.exception("Failed to initialize ChromaDB client: %s", exc)
            raise

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
            normalized_state = state.lower().strip().replace(" ", "-")
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

    def _detect_intent(self, query: str) -> Set[str]:
        detected: Set[str] = set()
        lowered = clean_text(query).lower()

        for category, triggers in INTENT_KEYWORDS.items():
            for trigger in triggers:
                if trigger in lowered:
                    detected.add(category)
                    break

        return detected

    @staticmethod
    def _tokenize(query: str) -> Set[str]:
        return {
            token
            for token in clean_text(query).lower().split()
            if len(token) > 2
        }

    @staticmethod
    def _field_text(metadata: Dict[str, Any], field: str) -> str:
        value = metadata.get(field, "")

        if isinstance(value, (list, tuple, set)):
            return clean_text(" ".join(str(v) for v in value)).lower()

        return clean_text(str(value)).lower()

    def _score_document(
        self,
        tokens: Set[str],
        document: str,
        metadata: Dict[str, Any],
        detected_categories: Set[str],
    ) -> float:
        score = 0.0

        field_texts: Dict[str, str] = {
            field: self._field_text(metadata, field)
            for field in FIELD_WEIGHTS
        }
        field_texts["description"] = (
            field_texts.get("description", "") or clean_text(document).lower()
        )

        for field, weight in FIELD_WEIGHTS.items():
            text = field_texts.get(field, "")
            if not text:
                continue

            words = text.split()

            for token in tokens:
                if token in text:
                    score += weight
                    continue

                for word in words:
                    if len(word) < 3:
                        continue
                    ratio = difflib.SequenceMatcher(None, token, word).ratio()
                    if ratio > FUZZY_THRESHOLD:
                        score += weight * FUZZY_PARTIAL_MULTIPLIER
                        break

        if detected_categories:
            category_value = str(metadata.get("category", "")).lower().strip()
            if category_value in detected_categories:
                score += FIELD_WEIGHTS["scheme_name"]

        return score

    def _get_all_items(
        self,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
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
            document = documents[idx] if idx < len(documents) else ""
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            items.append(
                {
                    "id": doc_id,
                    "document": document or "",
                    "metadata": metadata or {},
                }
            )

        return items

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
            results = self._collection.query(
                query_texts=[query],
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
                similarity = 1.0 - float(distance)
            except (TypeError, ValueError):
                similarity = 0.0

            similarity = max(0.0, min(1.0, similarity))

            output.append(
                {
                    "document": document or "",
                    "metadata": metadata or {},
                    "score": similarity,
                }
            )

        return output

    def search_keyword(
        self,
        query: str,
        where: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            logger.warning("search_keyword called with empty query")
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        detected_categories = self._detect_intent(query)

        items = self._get_all_items(where=where)
        if not items:
            return []

        scored: List[Dict[str, Any]] = []

        for item in items:
            score = self._score_document(
                tokens=tokens,
                document=item["document"],
                metadata=item["metadata"],
                detected_categories=detected_categories,
            )

            if score > 0:
                scored.append(
                    {
                        "document": item["document"],
                        "metadata": item["metadata"],
                        "score": score,
                    }
                )

        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:top_k]

    def search_by_state(
        self,
        query: str,
        state: str,
        top_k: int = 5,
        use_semantic: bool = True,
    ) -> List[Dict[str, Any]]:
        where = self._build_state_where(state=state, extra_where=None)

        if use_semantic:
            return self.search_semantic(query=query, where=where, top_k=top_k)

        return self.search_keyword(query=query, where=where, top_k=top_k)

    def search_by_category(
        self,
        query: str,
        category: str,
        top_k: int = 5,
        use_semantic: bool = True,
    ) -> List[Dict[str, Any]]:
        normalized_category = category.lower().strip().replace(" ", "-")
        where = {"category": normalized_category}

        if use_semantic:
            return self.search_semantic(query=query, where=where, top_k=top_k)

        return self.search_keyword(query=query, where=where, top_k=top_k)

    def get_scheme(self, scheme_id: str) -> Optional[Dict[str, Any]]:
        if not scheme_id:
            logger.warning("get_scheme called with empty scheme_id")
            return None

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
            return None

        return {
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

    def aggregate_ranked(
        self,
        ranked_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not ranked_chunks:
            return []

        best: Dict[str, Dict[str, Any]] = {}

        for row in ranked_chunks:
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

        return sorted(best.values(), key=lambda item: item["score"], reverse=True)


scheme_repository = SchemeRepository()
