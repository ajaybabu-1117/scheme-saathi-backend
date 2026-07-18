from fastapi import APIRouter

from app.schemas.notification import NotificationRequest
from app.services.notification_service import get_notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("")
def create_notification(payload: NotificationRequest):
    return get_notification_service().send(payload.model_dump())
