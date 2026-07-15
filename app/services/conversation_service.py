from app.models.conversation import ConversationState

conversations = {}


class ConversationService:
    def get(self, conversation_id: str):
        return conversations.get(conversation_id)

    def save(self, state: ConversationState):
        conversations[state.conversation_id] = state

    def delete(self, conversation_id: str):
        conversations.pop(conversation_id, None)


conversation_service = ConversationService()