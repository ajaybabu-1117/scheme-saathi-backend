from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.deps import get_optional_user_claims
from app.repositories.user_repository import user_repository
from app.schemas.profile import UserProfile
from app.schemas.voice import VoiceQueryResponse
from app.services.rag_service import rag_service
from app.services.voice_service import voice_service

router = APIRouter(prefix="/voice", tags=["Voice"])


@router.post("/query", response_model=VoiceQueryResponse)
async def voice_query(
    audio: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    language: str = Form(default="en"),
    claims=Depends(get_optional_user_claims),
):
    transcript = text
    if audio is not None:
        transcript = voice_service.transcribe(audio)
    if not transcript:
        raise HTTPException(status_code=400, detail="Provide either audio or text")

    profile = None
    if claims:
        stored = user_repository.get_profile(claims["sub"])
        if stored:
            profile = UserProfile(**stored)

    result = await rag_service.answer(query=transcript, language=language, user_profile=profile)
    audio_reply = voice_service.synthesize(result["answer"], language=language)
    return VoiceQueryResponse(transcript=transcript, answer=result["answer"], language=language, audio_reply_base64=audio_reply)
