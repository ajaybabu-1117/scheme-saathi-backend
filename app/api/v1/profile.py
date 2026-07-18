from fastapi import APIRouter, Depends

from app.core.deps import get_current_user_claims
from app.repositories.user_repository import get_user_repository
from app.schemas.profile import ProfileUpdateRequest, UserProfile

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_model=UserProfile)
def get_profile(claims=Depends(get_current_user_claims)):
    user_id = claims["sub"]
    profile = get_user_repository().get_profile(user_id) or {"user_id": user_id, "preferred_language": "en"}
    return UserProfile(**profile)


@router.put("", response_model=UserProfile)
def update_profile(payload: ProfileUpdateRequest, claims=Depends(get_current_user_claims)):
    user_id = claims["sub"]
    saved = get_user_repository().save_profile(user_id, payload.model_dump(exclude_none=True))
    return UserProfile(**saved)
