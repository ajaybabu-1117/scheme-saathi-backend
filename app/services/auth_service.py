from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from app.core.security import create_access_token
from app.models.enums import AuthProvider
from app.repositories.user_repository import get_user_repository
from app.schemas.auth import AuthLoginRequest
from app.utils.ids import generate_id


class AuthService:
    def anonymous_login(self):
        user_id = generate_id("anon")
        get_user_repository().save_user(
            user_id,
            {
                "user_id": user_id,
                "provider": AuthProvider.anonymous.value,
                "is_anonymous": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        token = create_access_token(user_id, {"provider": AuthProvider.anonymous.value, "is_anonymous": True})
        return {"access_token": token, "user_id": user_id, "provider": AuthProvider.anonymous.value, "is_anonymous": True}

    def login(self, payload: AuthLoginRequest):
        if payload.provider == AuthProvider.google:
            user_id = generate_id("google")
            email = payload.email or "google-user@example.com"
            name = payload.name or "Google User"
        else:
            user_id = generate_id("user")
            email = str(payload.email or "demo@example.com")
            name = payload.name or email.split("@")[0]
        get_user_repository().save_user(
            user_id,
            {
                "user_id": user_id,
                "provider": payload.provider.value,
                "email": email,
                "name": name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        token = create_access_token(user_id, {"provider": payload.provider.value, "email": email, "name": name, "is_anonymous": False})
        return {"access_token": token, "user_id": user_id, "provider": payload.provider.value, "is_anonymous": False}


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()
