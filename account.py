from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
import re

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.article import Article

router = APIRouter()


def validate_email(email: str) -> str:
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValueError('Érvénytelen e-mail cím')
    return email.lower().strip()


class AccountResponse(BaseModel):
    id:                 str
    email:              str
    first_name:         str
    last_name:          str
    website:            str
    plan:               str
    trial_ends_at:      Optional[datetime]
    articles_used:      int
    articles_limit:     int
    articles_remaining: int
    created_at:         datetime


class AccountUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    website:    Optional[str] = None
    email:      Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def check_email(cls, v):
        if v is None:
            return v
        return validate_email(v)


@router.get("", response_model=AccountResponse)
async def get_account(current_user: User = Depends(get_current_user)):
    return AccountResponse(
        id=current_user.id, email=current_user.email,
        first_name=current_user.first_name, last_name=current_user.last_name,
        website=current_user.website, plan=current_user.plan,
        trial_ends_at=current_user.trial_ends_at,
        articles_used=current_user.articles_used_this_month,
        articles_limit=current_user.article_limit,
        articles_remaining=current_user.articles_remaining,
        created_at=current_user.created_at,
    )


@router.patch("", response_model=AccountResponse)
async def update_account(req: AccountUpdateRequest, current_user: User=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    if req.first_name is not None: current_user.first_name = req.first_name
    if req.last_name  is not None: current_user.last_name  = req.last_name
    if req.website    is not None: current_user.website    = req.website
    if req.email      is not None:
        existing = await db.execute(select(User).where(User.email==req.email, User.id!=current_user.id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Ez az e-mail cím már foglalt")
        current_user.email = req.email
    await db.commit()
    await db.refresh(current_user)
    return await get_account(current_user)


@router.get("/stats")
async def get_stats(current_user: User=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    total     = await db.execute(select(func.count()).where(Article.user_id==current_user.id))
    published = await db.execute(select(func.count()).where(Article.user_id==current_user.id, Article.status=="published"))
    avg_seo   = await db.execute(select(func.avg(Article.seo_score)).where(Article.user_id==current_user.id))
    return {
        "total_articles":      total.scalar() or 0,
        "published_articles":  published.scalar() or 0,
        "avg_seo_score":       round(avg_seo.scalar() or 0, 1),
        "articles_this_month": current_user.articles_used_this_month,
        "articles_remaining":  current_user.articles_remaining,
        "plan":                current_user.plan,
    }
