from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.database.firebase import firebase_client


class RecommendationRepository:
    def save(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload.update({"user_id": user_id, "updated_at": datetime.now(timezone.utc).isoformat()})
        return firebase_client.upsert_document("recommendations", user_id, payload)


recommendation_repository = RecommendationRepository()
