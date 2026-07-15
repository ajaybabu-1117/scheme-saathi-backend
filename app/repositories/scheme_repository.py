from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.database.chromadb import chroma_client
from app.utils.text import clean_text


class SchemeRepository:
    def search_semantic(self, query: str, where: Dict[str, Any] | None = None, top_k: int = 5) -> List[Dict[str, Any]]:
        results = chroma_client.query([query], n_results=top_k, where=where)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        items: List[Dict[str, Any]] = []
        for doc, meta, distance in zip(documents, metadatas, distances):
            score = 1 / (1 + float(distance or 0))
            items.append({"document": doc, "metadata": meta, "score": score})
        return items

    def list_chunks(self, where: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        raw = chroma_client.get(where=where)
        docs = raw.get("documents", [])
        metas = raw.get("metadatas", [])
        ids = raw.get("ids", [])
        return [{"id": _id, "document": doc, "metadata": meta} for _id, doc, meta in zip(ids, docs, metas)]

    def search_keyword(self, query: str, where: Dict[str, Any] | None = None, top_k: int = 5) -> List[Dict[str, Any]]:
        tokens = {token for token in clean_text(query).lower().split() if len(token) > 2}
        scored: List[Dict[str, Any]] = []
        for item in self.list_chunks(where=where):
            haystack = clean_text(item["document"]).lower()
            overlap = sum(1 for token in tokens if token in haystack)
            if overlap:
                scored.append({"document": item["document"], "metadata": item["metadata"], "score": float(overlap)})
        return sorted(scored, key=lambda row: row["score"], reverse=True)[:top_k]

    def get_scheme(self, scheme_id: str) -> Optional[Dict[str, Any]]:
        chunks = self.list_chunks(where={"scheme_id": scheme_id})
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
            "chunks": [chunk["document"] for chunk in chunks],
        }

    def aggregate_ranked(self, ranked_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best: Dict[str, Dict[str, Any]] = {}
        for row in ranked_chunks:
            meta = row["metadata"]
            scheme_id = meta.get("scheme_id") or meta.get("id")
            current = best.get(scheme_id)
            payload = {
                "scheme_id": scheme_id,
                "scheme_name": meta.get("scheme_name"),
                "state": meta.get("state"),
                "category": meta.get("category"),
                "level": meta.get("level"),
                "website": meta.get("website"),
                "score": row["score"],
                "snippet": row["document"][:240],
                "metadata": meta,
            }
            if not current or payload["score"] > current["score"]:
                best[scheme_id] = payload
        return sorted(best.values(), key=lambda item: item["score"], reverse=True)


scheme_repository = SchemeRepository()
