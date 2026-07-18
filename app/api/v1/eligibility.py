from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_optional_user_claims
from app.repositories.scheme_repository import get_scheme_repository
from app.repositories.user_repository import get_user_repository
from app.schemas.eligibility import EligibilityCheckRequest, EligibilityCheckResponse
from app.schemas.profile import UserProfile
from app.services.eligibility_service import get_eligibility_service

router = APIRouter(prefix="/eligibility", tags=["Eligibility"])


@router.post("/check", response_model=EligibilityCheckResponse)
def check_eligibility(payload: EligibilityCheckRequest, claims=Depends(get_optional_user_claims)):
    scheme = get_scheme_repository().get_scheme(payload.scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    profile = payload.profile
    if profile is None and claims:
        stored = get_user_repository().get_profile(claims["sub"])
        if stored:
            profile = UserProfile(**stored)
    if profile is None:
        raise HTTPException(status_code=400, detail="Profile payload or authenticated profile is required")

    result = get_eligibility_service().check(profile, scheme)
    return EligibilityCheckResponse(scheme_id=payload.scheme_id, **result)
