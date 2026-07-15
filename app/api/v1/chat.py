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
from app.services.translation_service import translation_service
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
    # Get Conversation Memory
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
    # State Detection
    # -------------------------
    if not conversation.state:

        detected_state = (
            payload.state
            or detect_state(payload.message)
        )

        if detected_state:
            conversation.state = detected_state
            conversation.awaiting = None

        else:
            conversation.awaiting = "state"
            conversation_service.save(conversation)

            answer = translation_service.translate_from_english(
                "Please tell me your state so I can recommend schemes specific to your state.",
                target_language=conversation.language,
            )

            return ChatResponse(
                answer=answer,
                detected_state=None,
                citations=[],
                conversation_id=conversation_id,
            )

    # -------------------------
    # Save Conversation State
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
        state=conversation.state,
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

    analytics_service.log_chat(
        payload.message,
        conversation_id,
        user_id,
    )

    return ChatResponse(
        answer=result["answer"],
        detected_state=conversation.state,
        citations=result["citations"],
        conversation_id=conversation_id,
    )