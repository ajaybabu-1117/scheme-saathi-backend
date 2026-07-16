from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from app.database.chromadb import chroma_client
from app.utils.text import clean_text


class SchemeRepository:
    # -----------------------------
    # Utility Functions
    # -----------------------------
    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []

        return [
            token
            for token in clean_text(text).lower().split()
            if len(token) > 2
        ]

    def _fuzzy_score(self, query: str, text: str) -> float:
        if not query or not text:
            return 0.0

        return SequenceMatcher(
            None,
            query.lower(),
            text.lower()
        ).ratio()

    # -----------------------------
    # Semantic Search
    # -----------------------------
    def search_semantic(
        self,
        query: str,
        where: Dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:

        results = chroma_client.query(
            [query],
            n_results=top_k,
            where=where,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        items: List[Dict[str, Any]] = []

        for doc, meta, distance in zip(
            documents,
            metadatas,
            distances,
        ):
            semantic_score = 1 / (1 + float(distance or 0))

            items.append(
                {
                    "document": doc,
                    "metadata": meta,
                    "score": semantic_score,
                }
            )

        return items

    # -----------------------------
    # List Chunks
    # -----------------------------
    def list_chunks(
        self,
        where: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:

        raw = chroma_client.get(where=where)

        docs = raw.get("documents", [])
        metas = raw.get("metadatas", [])
        ids = raw.get("ids", [])

        return [
            {
                "id": _id,
                "document": doc,
                "metadata": meta,
            }
            for _id, doc, meta in zip(ids, docs, metas)
        ]

    # -----------------------------
    # Advanced Keyword Search
    # -----------------------------
    def search_keyword(
        self,
        query: str,
        where: Dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:

        query_tokens = self._tokenize(query)
        query_text = " ".join(query_tokens)

        scored = []

        for item in self.list_chunks(where=where):
            document = item["document"] or ""
            metadata = item["metadata"] or {}

            text = clean_text(document).lower()

            scheme_name = (
                metadata.get("scheme_name", "")
            ).lower()

            category = (
                metadata.get("category", "")
            ).lower()

            state = (
                metadata.get("state", "")
            ).lower()

            benefits = (
                metadata.get("benefits", "")
            ).lower()

            tags = metadata.get("tags", [])

            if isinstance(tags, str):
                tags = [tags]

            tags_text = " ".join(tags).lower()

            score = 0.0

            # ---------------------------------
            # Exact Keyword Matching
            # ---------------------------------
            for token in query_tokens:
                if token in scheme_name:
                    score += 5

                if token in tags_text:
                    score += 4

                if token in benefits:
                    score += 4

                if token in category:
                    score += 3

                if token in state:
                    score += 2

                if token in text:
                    score += 1

            # ---------------------------------
            # Fuzzy Matching
            # ---------------------------------
            fuzzy_name = self._fuzzy_score(
                query_text,
                scheme_name,
            )

            fuzzy_text = self._fuzzy_score(
                query_text,
                text[:1000],
            )

            score += fuzzy_name * 10
            score += fuzzy_text * 5

            # ---------------------------------
            # Bonus for multiple matches
            # ---------------------------------
            overlap = sum(
                1
                for token in query_tokens
                if token in text
            )

            if overlap >= 3:
                score += 5
            elif overlap >= 2:
                score += 2

            if score > 0:
                scored.append(
                    {
                        "document": document,
                        "metadata": metadata,
                        "score": round(score, 4),
                    }
                )

        return sorted(
            scored,
            key=lambda row: row["score"],
            reverse=True,
        )[:top_k]

    # -----------------------------
    # Get Scheme
    # -----------------------------
    def get_scheme(
        self,
        scheme_id: str,
    ) -> Optional[Dict[str, Any]]:

        chunks = self.list_chunks(
            where={"scheme_id": scheme_id}
        )

        if not chunks:
            return None

        first = chunks[0]["metadata"]

        return {
            "scheme_id": scheme_id,
            "scheme_name": first.get("scheme_name"),
            "description": chunks[0]["document"],
            "state": first.get("state"),
            "category": first.get("category"),
            "level": first.get("level"),
            "website": first.get("website"),
            "last_updated": first.get("last_updated"),
            "source_file": first.get("source_file"),
            "metadata": first,
            "chunks": [
                chunk["document"]
                for chunk in chunks
            ],
        }

    # -----------------------------
    # Aggregate + Ranking
    # -----------------------------
    def aggregate_ranked(
        self,
        ranked_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        grouped: Dict[str, Dict[str, Any]] = {}

        for row in ranked_chunks:
            meta = row["metadata"]

            scheme_id = (
                meta.get("scheme_id")
                or meta.get("id")
            )

            if not scheme_id:
                continue

            if scheme_id not in grouped:
                grouped[scheme_id] = {
                    "scheme_id": scheme_id,
                    "scheme_name": meta.get(
                        "scheme_name"
                    ),
                    "state": meta.get("state"),
                    "category": meta.get(
                        "category"
                    ),
                    "level": meta.get("level"),
                    "website": meta.get(
                        "website"
                    ),
                    "score": 0.0,
                    "snippet": row["document"][:240],
                    "metadata": meta,
                    "matches": 0,
                }

            grouped[scheme_id]["score"] += row[
                "score"
            ]
            grouped[scheme_id]["matches"] += 1

        results = []

        for item in grouped.values():
            # Bonus for multiple matching chunks
            item["score"] += (
                item["matches"] * 0.5
            )

            item["score"] = round(
                item["score"],
                4,
            )

            del item["matches"]

            results.append(item)

        return sorted(
            results,
            key=lambda x: x["score"],
            reverse=True,
        )


scheme_repository = SchemeRepository()