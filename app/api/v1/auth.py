from fastapi import APIRouter

from app.schemas.auth import AuthLoginRequest, AuthResponse
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest):
    return auth_service.login(payload)


@router.post("/anonymous", response_model=AuthResponse)
def anonymous_login():
    return auth_service.anonymous_login()
