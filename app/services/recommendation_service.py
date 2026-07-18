from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

from app.repositories.recommendation_repository import get_recommendation_repository
from app.repositories.scheme_repository import get_scheme_repository
from app.schemas.profile import UserProfile
from app.services.eligibility_service import get_eligibility_service


class RecommendationService:
    def recommend(self, user_id: str, profile: UserProfile, top_k: int = 5) -> List[Dict[str, Any]]:
        state_filter = profile.state.lower() if profile.state else None
        chunks = get_scheme_repository().list_chunks(where={"state": state_filter} if state_filter else None)
        ranked: List[Dict[str, Any]] = []
        for chunk in chunks:
            scheme = get_scheme_repository().get_scheme(chunk["metadata"].get("scheme_id"))
            if not scheme:
                continue
            result = get_eligibility_service().check(profile, scheme)
            base = 0.3 + result["confidence"]
            if result["eligible"] is False:
                base -= 0.5
            ranked.append(
                {
                    "scheme_id": scheme["scheme_id"],
                    "scheme_name": scheme["scheme_name"],
                    "state": scheme.get("state"),
                    "category": scheme.get("category"),
                    "level": scheme.get("level"),
                    "website": scheme.get("website"),
                    "score": round(base, 3),
                    "snippet": scheme.get("description", "")[:240],
                    "metadata": scheme.get("metadata", {}),
                }
            )
        dedup = {item["scheme_id"]: item for item in sorted(ranked, key=lambda row: row["score"], reverse=True)}
        recommendations = list(dedup.values())[:top_k]
        get_recommendation_repository().save(user_id, {"recommendations": recommendations})
        return recommendations


@lru_cache
def get_recommendation_service() -> RecommendationService:
    return RecommendationService()
