from typing import List

from pydantic import BaseModel

from app.schemas.scheme import SchemeSearchResponseItem


class RecommendationResponse(BaseModel):
    user_id: str
    recommendations: List[SchemeSearchResponseItem]
