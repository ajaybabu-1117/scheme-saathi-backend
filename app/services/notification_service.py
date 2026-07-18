from __future__ import annotations

from functools import lru_cache

from app.repositories.notification_repository import get_notification_repository


class NotificationService:
    def send(self, payload: dict) -> dict:
        stored = get_notification_repository().save({**payload, "status": "queued"})
        return {"status": "queued", "notification": stored}


@lru_cache
def get_notification_service() -> NotificationService:
    return NotificationService()
