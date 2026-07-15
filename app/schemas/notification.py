from typing import Any, Dict, Optional

from pydantic import BaseModel


class NotificationRequest(BaseModel):
    user_id: str
    title: str
    body: str
    token: Optional[str] = None
    data: Dict[str, Any] = {}
