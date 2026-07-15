from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    language: str = "en"
    conversation_id: Optional[str] = None
    state: Optional[str] = None
    filters: Dict[str, Any] | None = None


class Citation(BaseModel):
    scheme_id: str
    scheme_name: str
    website: Optional[str] = None
    source_file: Optional[str] = None
    state: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    detected_state: Optional[str] = None
    citations: List[Citation] = []
    conversation_id: Optional[str] = None
