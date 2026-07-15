from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.enums import AuthProvider


class AuthLoginRequest(BaseModel):
    provider: AuthProvider
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    id_token: Optional[str] = None
    name: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    provider: str
    is_anonymous: bool = False
