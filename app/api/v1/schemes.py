from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.repositories.scheme_repository import get_scheme_repository
from app.schemas.scheme import SchemeDetailResponse, SchemeSearchResponseItem
from app.services.analytics_service import get_analytics_service
from app.services.rag_service import get_rag_service

router = APIRouter(prefix="/schemes", tags=["Schemes"])


@router.get("/search", response_model=List[SchemeSearchResponseItem])
def search_schemes(
    q: str = Query(..., description="Search query"),
    state: Optional[str] = None,
    category: Optional[str] = None,
    level: Optional[str] = None,
    top_k: int = 10,
):
    items = get_rag_service().retrieve(q, state=state, filters={"category": category, "level": level}, top_k=top_k)
    get_analytics_service().log_search(q, state, items)
    return [SchemeSearchResponseItem(**item) for item in items]


@router.get("/{scheme_id}", response_model=SchemeDetailResponse)
def get_scheme(scheme_id: str):
    scheme = get_scheme_repository().get_scheme(scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return SchemeDetailResponse(**scheme)
