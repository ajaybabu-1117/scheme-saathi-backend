from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from app.core.config import BASE_DIR, get_settings


class LocalJsonStore:
    def __init__(self, path: Path | None = None):
        self.path = path or BASE_DIR / "data" / "mock_db.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _read(self) -> Dict[str, Dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8") or "{}")

    def _write(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            data = self._read()
            return data.get(collection, {}).get(doc_id)

    def upsert(self, collection: str, doc_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            data = self._read()
            bucket = data.setdefault(collection, {})
            current = bucket.get(doc_id, {})
            current.update(payload)
            bucket[doc_id] = current
            self._write(data)
            return current

    def delete(self, collection: str, doc_id: str) -> None:
        with self.lock:
            data = self._read()
            if collection in data and doc_id in data[collection]:
                del data[collection][doc_id]
                self._write(data)

    def list(self, collection: str, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        with self.lock:
            data = self._read()
            values = list(data.get(collection, {}).values())
            if not filters:
                return values
            result = []
            for item in values:
                if all(item.get(key) == value for key, value in filters.items()):
                    result.append(item)
            return result


class FirebaseClient:
    def __init__(self):
        self.settings = get_settings()
        self.store = LocalJsonStore()

    def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get(collection, doc_id)

    def upsert_document(self, collection: str, doc_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.store.upsert(collection, doc_id, payload)

    def list_documents(self, collection: str, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        return self.store.list(collection, filters)

    def delete_document(self, collection: str, doc_id: str) -> None:
        self.store.delete(collection, doc_id)


@lru_cache
def get_firebase_client() -> FirebaseClient:
    return FirebaseClient()
