from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Dict, List

import chromadb

from app.core.config import get_settings


class SimpleEmbeddingFunction:
    def __call__(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            bucket = [0.0] * 64
            for idx, char in enumerate(text.lower()[:2048]):
                bucket[(idx + ord(char)) % 64] += 1.0
            norm = math.sqrt(sum(value * value for value in bucket)) or 1.0
            vectors.append([value / norm for value in bucket])
        return vectors

@lru_cache
def get_embedding_function():
    settings = get_settings()

    if settings.app_env == "production":
        return SimpleEmbeddingFunction()

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )

class ChromaClient:
    def __init__(self):
        settings = get_settings()
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            embedding_function=get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, ids: List[str], documents: List[str], metadatas: List[Dict[str, Any]]) -> None:
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, query_texts: List[str], n_results: int = 5, where: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.collection.query(query_texts=query_texts, n_results=n_results, where=where)

    def get(self, ids: List[str] | None = None, where: Dict[str, Any] | None = None, limit: int | None = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if ids:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if limit:
            kwargs["limit"] = limit
        return self.collection.get(**kwargs)

    def delete(self, ids: List[str] | None = None, where: Dict[str, Any] | None = None) -> None:
        if ids:
            self.collection.delete(ids=ids)
            return
        if where:
            self.collection.delete(where=where)
            return
        existing = self.collection.get()
        existing_ids = existing.get("ids", []) if existing else []
        if existing_ids:
            self.collection.delete(ids=existing_ids)

    def count(self) -> int:
        return self.collection.count()


chroma_client = ChromaClient()
