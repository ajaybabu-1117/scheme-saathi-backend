from pydantic import BaseModel
from typing import Optional


class ConversationState(BaseModel):
    conversation_id: str
    state: Optional[str] = None
    category: Optional[str] = None
    occupation: Optional[str] = None
    language: str = "en"
    awaiting: Optional[str] = None