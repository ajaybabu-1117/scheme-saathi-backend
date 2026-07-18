from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List

from app.database.firebase import get_firebase_client
from app.utils.ids import generate_id


class AnalyticsRepository:
    def log_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_id = generate_id("evt")
        payload.update({"event_id": event_id, "event_type": event_type, "created_at": datetime.now(timezone.utc).isoformat()})
        return get_firebase_client().upsert_document("analytics", event_id, payload)

    def list_events(self) -> List[Dict[str, Any]]:
        return get_firebase_client().list_documents("analytics")


@lru_cache
def get_analytics_repository() -> AnalyticsRepository:
    return AnalyticsRepository()
