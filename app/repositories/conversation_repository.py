from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

from app.database.firebase import get_firebase_client
from app.utils.ids import generate_id


class ConversationRepository:
    def create_if_missing(self, conversation_id: str | None, user_id: str | None) -> str:
        if conversation_id:
            existing = get_firebase_client().get_document("conversations", conversation_id)
            if existing:
                return conversation_id
        conversation_id = generate_id("conv")
        get_firebase_client().upsert_document(
            "conversations",
            conversation_id,
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return conversation_id

    def add_message(self, conversation_id: str, role: str, content: str) -> Dict[str, Any]:
        message_id = generate_id("msg")
        return get_firebase_client().upsert_document(
            "messages",
            message_id,
            {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )


@lru_cache
def get_conversation_repository() -> ConversationRepository:
    return ConversationRepository()
