from typing import Optional

from pydantic import BaseModel


class VoiceQueryResponse(BaseModel):
    transcript: Optional[str] = None
    answer: str
    language: str = "en"
    audio_reply_base64: Optional[str] = None
