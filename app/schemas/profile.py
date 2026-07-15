from typing import Optional

from pydantic import BaseModel


class UserProfile(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    state: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    income: Optional[float] = None
    caste: Optional[str] = None
    disability: Optional[bool] = None
    preferred_language: str = "en"


class ProfileUpdateRequest(UserProfile):
    pass
