from __future__ import annotations

from typing import Any, Dict, Optional

from app.database.firebase import firebase_client


class UserRepository:
    users_collection = "users"
    profiles_collection = "profiles"

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return firebase_client.get_document(self.users_collection, user_id)

    def save_user(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return firebase_client.upsert_document(self.users_collection, user_id, payload)

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return firebase_client.get_document(self.profiles_collection, user_id)

    def save_profile(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["user_id"] = user_id
        return firebase_client.upsert_document(self.profiles_collection, user_id, payload)


user_repository = UserRepository()
