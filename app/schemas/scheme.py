from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SchemeSearchResponseItem(BaseModel):
    scheme_id: str
    scheme_name: str
    state: Optional[str] = None
    category: Optional[str] = None
    level: Optional[str] = None
    website: Optional[str] = None
    score: float = 0.0
    snippet: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SchemeDetailResponse(BaseModel):
    scheme_id: str
    scheme_name: str
    description: str
    state: Optional[str] = None
    category: Optional[str] = None
    level: Optional[str] = None
    website: Optional[str] = None
    last_updated: Optional[str] = None
    source_file: Optional[str] = None
    metadata: Dict[str, Any] = {}
    chunks: List[str] = []
