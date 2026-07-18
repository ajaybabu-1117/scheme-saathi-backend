from app.models.conversation import ConversationState
from functools import lru_cache

conversations = {}


class ConversationService:
    def get(self, conversation_id: str):
        return conversations.get(conversation_id)

    def save(self, state: ConversationState):
        conversations[state.conversation_id] = state

    def delete(self, conversation_id: str):
        conversations.pop(conversation_id, None)


@lru_cache
def get_conversation_service() -> ConversationService:
    return ConversationService()