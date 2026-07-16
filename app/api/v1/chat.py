import logging
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

logger = logging.getLogger("scheme_saathi.chat")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

NO_STATE_FOLLOWUP = (
    "I couldn't find a specific scheme for that yet. "
    "Could you tell me your state, or add a bit more detail "
    "(e.g. your occupation or the type of help you need)?"
)


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
        try:
            stored_profile = user_repository.get_profile(user_id)
            if stored_profile:
                profile = UserProfile(**stored_profile)
        except Exception:
            # A profile lookup failure shouldn't block the chat — just
            # proceed as an anonymous/no-profile user.
            logger.exception("Failed to load profile for user_id=%s", user_id)

    # -------------------------
    # Conversation ID
    # -------------------------
    conversation_id = payload.conversation_id or str(uuid4())

    # -------------------------
    # Get / Initialize Conversation Memory
    # -------------------------
    conversation = conversation_service.get(conversation_id)

    if not conversation:
        conversation = ConversationState(
            conversation_id=conversation_id,
            language=payload.language or "en",
        )
        logger.info("Started new conversation conversation_id=%s", conversation_id)

    # -------------------------
    # Update Language
    # -------------------------
    if payload.language:
        conversation.language = payload.language

    # -------------------------
    # State Detection
    # -------------------------
    # CHANGED: state is now purely informational, never a hard gate.
    # - We still try to detect/update it every turn (so a user correcting
    #   or adding their state mid-conversation is picked up), but a missing
    #   state NEVER blocks the request or forces a "what's your state?"
    #   question. rag_service already returns central schemes plus any
    #   state-specific ones when a state IS known.
    detected_state = payload.state or detect_state(payload.message)

    if detected_state:
        if detected_state != conversation.state:
            logger.info(
                "State updated for conversation_id=%s: %s -> %s",
                conversation_id, conversation.state, detected_state,
            )
        conversation.state = detected_state
        conversation.awaiting = None
    elif not conversation.state and profile and profile.state:
        # Fall back to the user's saved profile state if the message/
        # payload didn't carry one — still never blocking.
        conversation.state = profile.state

    # -------------------------
    # Persist Conversation State
    # -------------------------
    try:
        conversation_service.save(conversation)
    except Exception:
        logger.exception("Failed to save conversation state for conversation_id=%s", conversation_id)

    # -------------------------
    # Save User Message
    # -------------------------
    try:
        conversation_repository.create_if_missing(conversation_id, user_id)
        conversation_repository.add_message(conversation_id, "user", payload.message)
    except Exception:
        # Losing chat history logging shouldn't stop the user getting an answer.
        logger.exception("Failed to persist user message for conversation_id=%s", conversation_id)

    # -------------------------
    # Call RAG (never blocked on missing state)
    # -------------------------
    try:
        result = await rag_service.answer(
            query=payload.message,
            language=conversation.language,
            user_profile=profile,
            state=conversation.state,
            filters=payload.filters,
        )
    except Exception:
        logger.exception("rag_service.answer failed for conversation_id=%s", conversation_id)
        try:
            fallback = translation_service.translate_from_english(
                "Sorry, something went wrong while looking that up. Please try again.",
                target_language=conversation.language,
            )
        except Exception:
            logger.exception("translate_from_english failed during error fallback")
            fallback = "Sorry, something went wrong while looking that up. Please try again."

        return ChatResponse(
            answer=fallback,
            detected_state=conversation.state,
            citations=[],
            conversation_id=conversation_id,
        )

    schemes_found = bool(result.get("citations") or result.get("results"))

    # -------------------------
    # Follow-up question — ONLY when truly nothing was found
    # -------------------------
    # CHANGED: this is now the *sole* trigger for asking the user anything.
    # We also avoid nagging: if we already asked last turn and still found
    # nothing, we don't ask again — we just return the "no schemes found"
    # answer from rag_service as-is.
    already_asked = conversation.awaiting == "state"

    if not schemes_found and not already_asked:
        conversation.awaiting = "state"
        try:
            conversation_service.save(conversation)
        except Exception:
            logger.exception("Failed to save conversation awaiting-state flag for conversation_id=%s", conversation_id)

        try:
            followup = translation_service.translate_from_english(
                NO_STATE_FOLLOWUP,
                target_language=conversation.language,
            )
        except Exception:
            logger.exception("translate_from_english failed for follow-up question")
            followup = NO_STATE_FOLLOWUP

        try:
            conversation_repository.add_message(conversation_id, "assistant", followup)
        except Exception:
            logger.exception("Failed to persist follow-up assistant message for conversation_id=%s", conversation_id)

        analytics_service.log_chat(payload.message, conversation_id, user_id)

        return ChatResponse(
            answer=followup,
            detected_state=conversation.state,
            citations=[],
            conversation_id=conversation_id,
        )

    # Clear the awaiting flag once we have something useful to say, so a
    # later empty result can trigger a fresh follow-up if needed.
    if conversation.awaiting:
        conversation.awaiting = None
        try:
            conversation_service.save(conversation)
        except Exception:
            logger.exception("Failed to clear awaiting flag for conversation_id=%s", conversation_id)

    # -------------------------
    # Save Assistant Message
    # -------------------------
    try:
        conversation_repository.add_message(
            conversation_id,
            "assistant",
            result["answer"],
        )
    except Exception:
        logger.exception("Failed to persist assistant message for conversation_id=%s", conversation_id)

    try:
        analytics_service.log_chat(payload.message, conversation_id, user_id)
    except Exception:
        logger.exception("analytics_service.log_chat failed for conversation_id=%s", conversation_id)

    return ChatResponse(
        answer=result["answer"],
        detected_state=conversation.state,
        citations=result["citations"],
        conversation_id=conversation_id,
    )