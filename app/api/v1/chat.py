from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

FALLBACK_ANSWER = "No relevant schemes found in the available database."


def _profile_to_dict(profile: UserProfile | None) -> Dict[str, Any]:
    if profile is None:
        return {}

    if hasattr(profile, "model_dump"):
        return profile.model_dump()

    return profile.dict()


def _get_profile_field_names() -> set[str]:
    if hasattr(UserProfile, "model_fields"):
        return set(UserProfile.model_fields.keys())

    return set(UserProfile.__fields__.keys())


def _extract_profile_updates(message: str) -> Dict[str, Any]:
    text = message.lower()
    updates: Dict[str, Any] = {}

    detected_state = detect_state(message)
    if detected_state:
        updates["state"] = detected_state

    city_match = re.search(r"\bi\s+live\s+in\s+([a-z][a-z\s]{2,30})", text)
    if not city_match:
        city_match = re.search(r"\bfrom\s+([a-z][a-z\s]{2,30})\b", text)

    if city_match:
        candidate = city_match.group(1).strip().title()
        if not detected_state or candidate.lower() != str(detected_state).lower():
            updates["city"] = candidate

    if re.search(r"\b(farmer|kisan|agriculture)\b", text):
        updates["occupation"] = "farmer"
    elif re.search(r"\b(student|scholar|pupil)\b", text):
        updates["occupation"] = "student"
    elif re.search(r"\b(business|entrepreneur|startup|self[\s-]employed)\b", text):
        updates["occupation"] = "business"
    elif re.search(r"\b(unemployed|jobless|job seeker)\b", text):
        updates["occupation"] = "unemployed"
    elif re.search(r"\b(employee|employed|salaried|working)\b", text):
        updates["occupation"] = "employed"

    if re.search(r"\b(woman|women|female|girl)\b", text):
        updates["gender"] = "female"
    elif re.search(r"\b(man|men|male|boy)\b", text):
        updates["gender"] = "male"

    age_match = re.search(
        r"\b(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|years?|yrs?)\b", text
    )
    if age_match:
        try:
            age_value = int(age_match.group(1))
        except ValueError:
            age_value = None

        if age_value is not None and 0 < age_value <= 120:
            updates["age"] = age_value
            if age_value >= 60:
                updates["senior_citizen"] = True

    income_match = re.search(
        r"\b(?:income|earn|earning|salary)[^\d]{0,20}(\d+(?:\.\d+)?)\s*(lakh|lakhs|thousand|crore)?",
        text,
    )
    if income_match:
        amount = income_match.group(1)
        unit = income_match.group(2) or ""
        updates["income"] = f"{amount} {unit}".strip()

    if re.search(r"\b(widow|widower)\b", text):
        updates["marital_status"] = "widow"
        updates["beneficiary_type"] = "widow"
    elif re.search(r"\bmarried\b", text):
        updates["marital_status"] = "married"
    elif re.search(r"\b(unmarried|single)\b", text):
        updates["marital_status"] = "single"

    if re.search(r"\b(disabled|disability|divyang|handicap)\b", text):
        updates["disability"] = True
        updates.setdefault("beneficiary_type", "disabled")

    if re.search(r"\b(senior citizen|old age|elderly|retired)\b", text):
        updates["senior_citizen"] = True
        updates.setdefault("beneficiary_type", "senior_citizen")

    category_match = re.search(r"\b(sc|st|obc|bc)\b", text)
    if category_match:
        code = category_match.group(1).upper()
        updates["category"] = code
        updates["caste_category"] = code

    if re.search(r"\b(graduate|post\s*graduate|phd|engineering)\b", text):
        updates["education"] = "higher"
    elif re.search(r"\b(school|primary|secondary)\b", text):
        updates["education"] = "school"

    if updates.get("occupation") in ("farmer", "student", "business"):
        updates.setdefault("beneficiary_type", updates["occupation"])

    return updates


def _merge_profile(
    profile: UserProfile | None,
    updates: Dict[str, Any],
) -> UserProfile | None:
    if not updates:
        return profile

    valid_fields = _get_profile_field_names()
    filtered_updates = {
        key: value
        for key, value in updates.items()
        if key in valid_fields and value is not None
    }

    if not filtered_updates:
        return profile

    base_data = _profile_to_dict(profile)
    base_data.update(filtered_updates)

    try:
        return UserProfile(**base_data)
    except Exception as exc:
        logger.warning("Failed to merge profile updates %s: %s", filtered_updates, exc)
        return profile


def _load_profile(user_id: str | None) -> UserProfile | None:
    if not user_id:
        return None

    try:
        stored_profile = user_repository.get_profile(user_id)
    except Exception as exc:
        logger.exception("Failed to load profile | user_id=%s error=%s", user_id, exc)
        return None

    if not stored_profile:
        return None

    try:
        return UserProfile(**stored_profile)
    except Exception as exc:
        logger.exception(
            "Failed to parse stored profile | user_id=%s error=%s", user_id, exc
        )
        return None


def _load_or_create_conversation(
    conversation_id: str,
    language: str | None,
) -> ConversationState:
    conversation = None

    try:
        conversation = conversation_service.get(conversation_id)
    except Exception as exc:
        logger.exception(
            "Failed to load conversation | conversation_id=%s error=%s",
            conversation_id,
            exc,
        )

    if not conversation:
        conversation = ConversationState(
            conversation_id=conversation_id,
            language=language or "en",
        )

    return conversation


def _safe_save_conversation(conversation: ConversationState) -> None:
    try:
        conversation_service.save(conversation)
    except Exception as exc:
        logger.exception(
            "Failed to save conversation | conversation_id=%s error=%s",
            conversation.conversation_id,
            exc,
        )


def _safe_record_user_message(
    conversation_id: str,
    user_id: str | None,
    message: str,
) -> None:
    try:
        conversation_repository.create_if_missing(conversation_id, user_id)
        conversation_repository.add_message(conversation_id, "user", message)
    except Exception as exc:
        logger.exception(
            "Failed to record user message | conversation_id=%s error=%s",
            conversation_id,
            exc,
        )


def _safe_record_assistant_message(conversation_id: str, answer: str) -> None:
    try:
        conversation_repository.add_message(conversation_id, "assistant", answer)
    except Exception as exc:
        logger.exception(
            "Failed to record assistant message | conversation_id=%s error=%s",
            conversation_id,
            exc,
        )


def _safe_log_analytics(
    message: str,
    conversation_id: str,
    user_id: str | None,
) -> None:
    try:
        analytics_service.log_chat(message, conversation_id, user_id)
    except Exception as exc:
        logger.exception(
            "Failed to log analytics | conversation_id=%s error=%s",
            conversation_id,
            exc,
        )


def _dedupe_citations(citations: Any) -> Any:
    if not citations:
        return []

    seen: set[str] = set()
    deduped = []

    for citation in citations:
        scheme_id = getattr(citation, "scheme_id", None)
        key = str(scheme_id) if scheme_id is not None else str(id(citation))

        if key in seen:
            continue

        seen.add(key)
        deduped.append(citation)

    return deduped


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    claims=Depends(get_optional_user_claims),
) -> ChatResponse:

    start_time = time.perf_counter()

    user_id = claims["sub"] if claims else None

    conversation_id = payload.conversation_id or str(uuid4())

    logger.info(
        "Chat request received | conversation_id=%s user_id=%s",
        conversation_id,
        user_id,
    )

    try:
        # -------------------------
        # Load User Profile
        # -------------------------
        profile = _load_profile(user_id)

        # -------------------------
        # Load Conversation
        # -------------------------
        conversation = _load_or_create_conversation(
            conversation_id, payload.language
        )

        # -------------------------
        # Update Language
        # -------------------------
        if payload.language:
            conversation.language = payload.language

        # -------------------------
        # Extract Information From Current Message
        # -------------------------
        profile_updates = _extract_profile_updates(payload.message)

        if profile_updates:
            logger.info(
                "Detected profile updates | conversation_id=%s updates=%s",
                conversation_id,
                profile_updates,
            )

        # -------------------------
        # Merge With Existing Profile
        # -------------------------
        profile = _merge_profile(profile, profile_updates)

        # -------------------------
        # Detect State
        # -------------------------
        detected_state = (
            payload.state
            or (profile.state if profile else None)
            or detect_state(payload.message)
            or conversation.state
        )

        if detected_state:
            conversation.state = detected_state

        conversation.awaiting = None

        logger.info(
            "Detected state=%s | conversation_id=%s",
            detected_state,
            conversation_id,
        )

        # -------------------------
        # Save Conversation
        # -------------------------
        _safe_save_conversation(conversation)

        # -------------------------
        # Save User Message
        # -------------------------
        _safe_record_user_message(conversation_id, user_id, payload.message)

        # -------------------------
        # Call RAG
        # -------------------------
        rag_start = time.perf_counter()

        try:
            result = await rag_service.answer(
                query=payload.message,
                language=conversation.language,
                user_profile=profile,
                state=conversation.state if conversation.state else None,
                filters=payload.filters,
            )
        except Exception as exc:
            logger.exception(
                "rag_service.answer failed | conversation_id=%s error=%s",
                conversation_id,
                exc,
            )
            result = {
                "answer": FALLBACK_ANSWER,
                "detected_state": detected_state,
                "citations": [],
                "results": [],
            }

        rag_duration = time.perf_counter() - rag_start

        logger.info(
            "RAG completed | conversation_id=%s duration=%.3fs retrieved=%d",
            conversation_id,
            rag_duration,
            len(result.get("results", []) or []),
        )

        # -------------------------
        # Save Assistant Message
        # -------------------------
        _safe_record_assistant_message(
            conversation_id, result.get("answer", FALLBACK_ANSWER)
        )

        # -------------------------
        # Analytics
        # -------------------------
        _safe_log_analytics(payload.message, conversation_id, user_id)

        # -------------------------
        # Citations
        # -------------------------
        citations = _dedupe_citations(result.get("citations", []))

        elapsed = time.perf_counter() - start_time

        logger.info(
            "Chat request completed | conversation_id=%s duration=%.3fs",
            conversation_id,
            elapsed,
        )

        # -------------------------
        # Response
        # -------------------------
        return ChatResponse(
            answer=result.get("answer", FALLBACK_ANSWER),
            detected_state=result.get("detected_state"),
            citations=citations,
            conversation_id=conversation_id,
        )

    except Exception as exc:
        logger.exception(
            "Unhandled error in chat endpoint | conversation_id=%s error=%s",
            conversation_id,
            exc,
        )
        return ChatResponse(
            answer=FALLBACK_ANSWER,
            detected_state=None,
            citations=[],
            conversation_id=conversation_id,
        )
