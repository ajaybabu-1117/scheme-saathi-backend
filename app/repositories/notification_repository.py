from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.database.firebase import firebase_client
from app.utils.ids import generate_id


class NotificationRepository:
    def save(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        notification_id = generate_id("notif")
        payload.update({"notification_id": notification_id, "created_at": datetime.now(timezone.utc).isoformat()})
        return firebase_client.upsert_document("notifications", notification_id, payload)


notification_repository = NotificationRepository()
