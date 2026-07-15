from typing import List, Optional

from pydantic import BaseModel

from app.schemas.profile import UserProfile


class EligibilityCheckRequest(BaseModel):
    scheme_id: str
    profile: Optional[UserProfile] = None


class EligibilityCheckResponse(BaseModel):
    scheme_id: str
    eligible: bool | None = None
    confidence: float = 0.0
    reasons: List[str] = []
