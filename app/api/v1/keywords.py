from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.core.subscription import has_active_access
from app.models.user import User
from app.services.ai_service import generate_keywords


router = APIRouter(prefix="/v1/keywords", tags=["keywords"])


class KeywordRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=120)
    industry: str | None = None


@router.post("/")
async def suggest_keywords(payload: KeywordRequest, user: User = Depends(get_current_user)):
    if not has_active_access(user):
        raise HTTPException(status_code=403, detail="Trial expired or subscription inactive. Please subscribe to continue.")
    try:
        return {"keywords": await generate_keywords(payload.keyword, payload.industry)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Keyword generation failed: {exc}") from exc
