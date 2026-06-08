import re
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.auth import get_current_user
from app.core.config import get_settings
from app.core.subscription import has_active_access, monthly_quota_for_user, sync_monthly_article_counter, trial_ends_at_utc
from app.core.database import get_db
from app.models.article import Article
from app.models.user import User


router = APIRouter(prefix="/v1/account", tags=["account"])
settings = get_settings()
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    first_name: str
    last_name: str
    website: str | None = None
    plan: str
    subscription_status: str
    trial_ends_at: datetime
    articles_used_this_month: int
    monthly_quota: int
    has_access: bool


class UpdateAccountIn(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=255)
    email: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


@router.get("/", response_model=AccountOut)
async def get_account(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sync_monthly_article_counter(user)
    await db.commit()
    await db.refresh(user)
    return AccountOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        website=user.website,
        plan=user.plan,
        subscription_status=user.subscription_status,
        trial_ends_at=trial_ends_at_utc(user),
        articles_used_this_month=user.articles_used_this_month,
        monthly_quota=monthly_quota_for_user(user, settings),
        has_access=has_active_access(user),
    )


@router.patch("/")
async def update_account(payload: UpdateAccountIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    for field in ("first_name", "last_name", "website", "email"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    await db.commit()
    return {"ok": True}


@router.get("/stats")
async def account_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(Article.id)).where(Article.user_id == user.id))
    published = await db.scalar(
        select(func.count(Article.id)).where(Article.user_id == user.id, Article.status == "published")
    )
    scheduled = await db.scalar(
        select(func.count(Article.id)).where(Article.user_id == user.id, Article.status == "scheduled")
    )
    return {"total_articles": total or 0, "published": published or 0, "scheduled": scheduled or 0}
