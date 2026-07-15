from pydantic import BaseModel


class AdminActionResponse(BaseModel):
    status: str
    detail: str
