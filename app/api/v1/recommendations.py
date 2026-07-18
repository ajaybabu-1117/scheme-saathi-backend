from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user_claims
from app.repositories.user_repository import get_user_repository
from app.schemas.profile import UserProfile
from app.schemas.recommendation import RecommendationResponse
from app.services.recommendation_service import get_recommendation_service

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("", response_model=RecommendationResponse)
def get_recommendations(claims=Depends(get_current_user_claims)):
    user_id = claims["sub"]
    profile = get_user_repository().get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Please update profile first")
    recommendations = get_recommendation_service().recommend(user_id, UserProfile(**profile), top_k=5)
    return RecommendationResponse(user_id=user_id, recommendations=recommendations)
