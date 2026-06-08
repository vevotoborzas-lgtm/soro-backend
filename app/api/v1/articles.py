import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.subscription import has_active_access, monthly_quota_for_user, sync_monthly_article_counter
from app.models.article import Article
from app.models.user import User
from app.services.ai_service import generate_article


router = APIRouter(prefix="/v1/articles", tags=["articles"])
settings = get_settings()


class GenerateArticleIn(BaseModel):
    topic: str
    word_count: Literal[800, 1200, 2000] = 1200
    tone: Literal["informative", "professional", "friendly", "persuasive"] = "informative"
    target_audience: str = ""
    include_faq: bool = False
    include_meta: bool = True
    target_site: str | None = None
    scheduled_at: datetime | None = None


class MarkPublishedIn(BaseModel):
    wp_post_id: str | None = None
    wp_post_url: str | None = None


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    excerpt: str
    focus_keyword: str
    seo_score: int
    word_count: int
    status: str
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    target_site: str | None = None


class ArticleFullOut(BaseModel):
    """Complete article row as returned after create or single-article fetch."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    content: str
    excerpt: str
    meta_title: str
    meta_description: str
    focus_keyword: str
    tags: list[str]
    seo_score: int
    word_count: int
    status: str
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    wp_post_id: str | None = None
    wp_post_url: str | None = None
    target_site: str | None = None
    created_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            try:
                parsed = json.loads(s)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []


@router.post("/generate", response_model=ArticleFullOut)
@limiter.limit("15/minute")
async def generate(
    request: Request,
    payload: GenerateArticleIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sync_monthly_article_counter(user)
    await db.commit()
    await db.refresh(user)

    if not has_active_access(user):
        raise HTTPException(status_code=403, detail="Trial expired or subscription inactive. Please subscribe to continue.")

    quota = monthly_quota_for_user(user, settings)
    if quota <= 0:
        raise HTTPException(status_code=403, detail="No article quota available for your account.")
    if user.articles_used_this_month >= quota:
        raise HTTPException(status_code=403, detail="Monthly quota reached")

    try:
        ai = await generate_article(
            payload.topic,
            target_site=payload.target_site,
            word_count=payload.word_count,
            tone=payload.tone,
            target_audience=payload.target_audience,
            include_faq=payload.include_faq,
            include_meta=payload.include_meta,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {exc}") from exc

    if not payload.include_meta:
        ai["meta_title"] = ""
        ai["meta_description"] = ""

    article = Article(
        user_id=user.id,
        title=ai.get("title", "Untitled"),
        content=ai.get("content", ""),
        excerpt=ai.get("excerpt", ""),
        meta_title=ai.get("meta_title", ""),
        meta_description=ai.get("meta_description", ""),
        focus_keyword=ai.get("focus_keyword", ""),
        tags=json.dumps(ai.get("tags", []), ensure_ascii=False),
        seo_score=int(ai.get("seo_score", 0)),
        word_count=int(ai.get("word_count", 0)),
        status="scheduled" if payload.scheduled_at else "draft",
        scheduled_at=payload.scheduled_at,
        target_site=payload.target_site,
    )
    db.add(article)
    user.articles_used_this_month += 1
    await db.commit()
    await db.refresh(article)
    return ArticleFullOut.model_validate(article)


@router.get("/", response_model=list[ArticleOut])
async def list_articles(
    status: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Article).where(Article.user_id == user.id)
    if status:
        stmt = stmt.where(Article.status == status)
    stmt = stmt.order_by(Article.created_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/scheduled")
async def scheduled(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    stmt = select(Article).where(
        Article.user_id == user.id,
        Article.status == "scheduled",
        Article.scheduled_at.is_not(None),
        Article.scheduled_at <= now,
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/{article_id}", response_model=ArticleFullOut)
async def get_article(article_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Article).where(Article.id == article_id, Article.user_id == user.id))
    article = res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.delete("/{article_id}")
async def delete_article(article_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Article).where(Article.id == article_id, Article.user_id == user.id))
    article = res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(article)
    await db.commit()
    return {"ok": True}


@router.post("/{article_id}/published")
async def mark_published(
    article_id: str,
    payload: MarkPublishedIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Article).where(Article.id == article_id, Article.user_id == user.id))
    article = res.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.status = "published"
    article.published_at = datetime.now(timezone.utc)
    article.wp_post_id = payload.wp_post_id
    article.wp_post_url = payload.wp_post_url
    await db.commit()
    return {"ok": True}


@router.get("/_stats/internal")
async def _internal_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Article.status, func.count(Article.id)).where(Article.user_id == user.id).group_by(Article.status)
    rows = (await db.execute(stmt)).all()
    return {row[0]: row[1] for row in rows}
