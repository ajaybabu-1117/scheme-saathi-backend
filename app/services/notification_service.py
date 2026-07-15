from __future__ import annotations

from app.repositories.notification_repository import notification_repository


class NotificationService:
    def send(self, payload: dict) -> dict:
        stored = notification_repository.save({**payload, "status": "queued"})
        return {"status": "queued", "notification": stored}


notification_service = NotificationService()
