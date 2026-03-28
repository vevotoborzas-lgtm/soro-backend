"""
app/api/v1/keywords.py – Kulcsszókutatás endpoint
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import get_current_user, require_active_subscription
from app.services.ai_service import suggest_keywords

router = APIRouter()


class KeywordRequest(BaseModel):
    topic:    str
    language: str = "hu"
    market:   str = "hu"
    limit:    int = 20


class KeywordItem(BaseModel):
    keyword:    str
    volume:     int
    difficulty: int
    cpc:        float
    trend:      str


@router.post("", response_model=list[KeywordItem])
async def get_keywords(
    req: KeywordRequest,
    current_user=Depends(require_active_subscription),
):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Téma megadása kötelező")

    keywords = await suggest_keywords(
        topic=req.topic,
        language=req.language,
        limit=min(req.limit, 50),
    )
    return keywords
