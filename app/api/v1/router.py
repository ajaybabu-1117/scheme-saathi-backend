from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, eligibility, notifications, profile, recommendations, schemes, voice

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(chat.router)
api_router.include_router(schemes.router)
api_router.include_router(recommendations.router)
api_router.include_router(eligibility.router)
api_router.include_router(voice.router)
api_router.include_router(notifications.router)
api_router.include_router(admin.router)
