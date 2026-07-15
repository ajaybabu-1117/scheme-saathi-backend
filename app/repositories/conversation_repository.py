from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.database.firebase import firebase_client
from app.utils.ids import generate_id


class ConversationRepository:
    def create_if_missing(self, conversation_id: str | None, user_id: str | None) -> str:
        if conversation_id:
            existing = firebase_client.get_document("conversations", conversation_id)
            if existing:
                return conversation_id
        conversation_id = generate_id("conv")
        firebase_client.upsert_document(
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
        return firebase_client.upsert_document(
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


conversation_repository = ConversationRepository()
