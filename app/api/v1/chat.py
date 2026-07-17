from uuid import uuid4

from fastapi import APIRouter, Depends

from app.core.deps import get_optional_user_claims
from app.models.conversation import ConversationState
from app.repositories.conversation_repository import conversation_repository
from app.repositories.user_repository import user_repository
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.profile import UserProfile
from app.services.analytics_service import analytics_service
from app.services.conversation_service import conversation_service
from app.services.rag_service import rag_service
from app.utils.states import detect_state

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    claims=Depends(get_optional_user_claims),
):
    user_id = claims["sub"] if claims else None

    # -------------------------
    # Load User Profile
    # -------------------------
    profile = None
    if user_id:
        stored_profile = user_repository.get_profile(user_id)
        if stored_profile:
            profile = UserProfile(**stored_profile)

    # -------------------------
    # Conversation ID
    # -------------------------
    conversation_id = (
        payload.conversation_id
        or str(uuid4())
    )

    # -------------------------
    # Load Conversation
    # -------------------------
    conversation = conversation_service.get(
        conversation_id
    )

    if not conversation:
        conversation = ConversationState(
            conversation_id=conversation_id,
            language=payload.language or "en",
        )

    # -------------------------
    # Update Language
    # -------------------------
    if payload.language:
        conversation.language = payload.language

    # -------------------------
    # Detect State (Optional)
    # -------------------------
    detected_state = (
        payload.state
        or detect_state(payload.message)
        or conversation.state
    )

    if detected_state:
        conversation.state = detected_state

    conversation.awaiting = None

    # -------------------------
    # Save Conversation
    # -------------------------
    conversation_service.save(conversation)

    # -------------------------
    # Save User Message
    # -------------------------
    conversation_repository.create_if_missing(
        conversation_id,
        user_id,
    )

    conversation_repository.add_message(
        conversation_id,
        "user",
        payload.message,
    )

    # -------------------------
    # Call RAG
    # -------------------------
    result = await rag_service.answer(
        query=payload.message,
        language=conversation.language,
        user_profile=profile,
        state=conversation.state if conversation.state else None,
        filters=payload.filters,
    )

    # -------------------------
    # Save Assistant Message
    # -------------------------
    conversation_repository.add_message(
        conversation_id,
        "assistant",
        result["answer"],
    )

    # -------------------------
    # Analytics
    # -------------------------
    analytics_service.log_chat(
        payload.message,
        conversation_id,
        user_id,
    )

    # -------------------------
    # Response
    # -------------------------
    return ChatResponse(
        answer=result["answer"],
        detected_state=result.get("detected_state"),
        citations=result["citations"],
        conversation_id=conversation_id,
    )
