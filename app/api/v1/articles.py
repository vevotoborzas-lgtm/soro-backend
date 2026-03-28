from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import json

from app.core.database import get_db
from app.core.security import get_current_user, require_active_subscription
from app.models.user import User
from app.models.article import Article
from app.services.ai_service import generate_article

router = APIRouter()


# ── Sémák ─────────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    keyword:             str
    word_count:          int = 1200
    tone:                str = "informative"
    language:            str = "hu"
    include_faq:         bool = True
    include_meta:        bool = True
    secondary_keywords:  list[str] = []
    target_audience:     str = "kis- és középvállalkozók"
    industry:            str = ""
    scheduled_at:        Optional[datetime] = None
    target_site:         Optional[str] = None


class PublishedConfirmRequest(BaseModel):
    wp_post_id: int
    url:        str
    published_at: Optional[datetime] = None


class ArticleResponse(BaseModel):
    id:               str
    title:            str
    meta_title:       str
    meta_description: str
    excerpt:          str
    focus_keyword:    str
    tags:             list[str]
    content:          str
    seo_score:        float
    word_count:       int
    status:           str
    scheduled_at:     Optional[datetime]
    published_at:     Optional[datetime]
    wp_post_id:       Optional[int]
    wp_post_url:      Optional[str]
    created_at:       datetime


class ArticleListItem(BaseModel):
    id:            str
    title:         str
    focus_keyword: str
    seo_score:     float
    word_count:    int
    status:        str
    scheduled_at:  Optional[datetime]
    published_at:  Optional[datetime]
    target_site:   Optional[str]
    created_at:    datetime


# ── Cikk generálás ────────────────────────────────────────────────────────────
@router.post("/generate", response_model=ArticleResponse, status_code=201)
async def generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.can_generate_article():
        raise HTTPException(
            status_code=429,
            detail=f"Elérted a havi limitedet ({current_user.article_limit} cikk). "
                   f"Váltj magasabb csomagra, vagy várj a kvóta visszaállításáig."
        )

    try:
        ai_result = await generate_article(
            keyword=req.keyword,
            word_count=req.word_count,
            tone=req.tone,
            include_faq=req.include_faq,
            include_meta=req.include_meta,
            secondary_keywords=req.secondary_keywords,
            target_audience=req.target_audience,
            industry=req.industry,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Mentés DB-be
    article = Article(
        user_id=current_user.id,
        title=ai_result["title"],
        content=ai_result["content"],
        excerpt=ai_result["excerpt"],
        meta_title=ai_result["meta_title"],
        meta_description=ai_result["meta_description"],
        focus_keyword=ai_result["focus_keyword"],
        tags=json.dumps(ai_result.get("tags", []), ensure_ascii=False),
        seo_score=ai_result["seo_score"],
        word_count=ai_result["word_count"],
        language=req.language,
        status="scheduled" if req.scheduled_at else "draft",
        scheduled_at=req.scheduled_at,
        target_site=req.target_site,
    )
    db.add(article)

    # Kvóta növelés
    current_user.articles_used_this_month += 1
    await db.commit()
    await db.refresh(article)

    return _to_response(article)


# ── Ütemezett cikkek (WordPress plugin kéri) ─────────────────────────────────
@router.get("/scheduled", response_model=list[ArticleListItem])
async def get_scheduled(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Article)
        .where(
            Article.user_id == current_user.id,
            Article.status == "scheduled",
        )
        .order_by(Article.scheduled_at.asc())
        .limit(20)
    )
    articles = result.scalars().all()
    return [_to_list_item(a) for a in articles]


# ── Publikálás visszajelzés ───────────────────────────────────────────────────
@router.post("/{article_id}/published", status_code=200)
async def confirm_published(
    article_id: str,
    req: PublishedConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article = await _get_article_or_404(article_id, current_user.id, db)
    article.status       = "published"
    article.wp_post_id   = req.wp_post_id
    article.wp_post_url  = req.url
    article.published_at = req.published_at or datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Publikálás visszaigazolva"}


# ── Cikk lista ────────────────────────────────────────────────────────────────
@router.get("", response_model=list[ArticleListItem])
async def list_articles(
    status: Optional[str] = None,
    limit:  int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Article).where(Article.user_id == current_user.id)
    if status:
        q = q.where(Article.status == status)
    q = q.order_by(Article.created_at.desc()).limit(min(limit, 100)).offset(offset)
    result = await db.execute(q)
    return [_to_list_item(a) for a in result.scalars().all()]


# ── Egy cikk lekérése ─────────────────────────────────────────────────────────
@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article = await _get_article_or_404(article_id, current_user.id, db)
    return _to_response(article)


# ── Cikk törlése ──────────────────────────────────────────────────────────────
@router.delete("/{article_id}", status_code=204)
async def delete_article(
    article_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article = await _get_article_or_404(article_id, current_user.id, db)
    await db.delete(article)
    await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _get_article_or_404(article_id: str, user_id: str, db: AsyncSession) -> Article:
    result = await db.execute(
        select(Article).where(Article.id == article_id, Article.user_id == user_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Cikk nem található")
    return article

def _parse_tags(tags_str: str) -> list[str]:
    try:
        return json.loads(tags_str) if tags_str else []
    except Exception:
        return [t.strip() for t in tags_str.split(",") if t.strip()]

def _to_response(a: Article) -> ArticleResponse:
    return ArticleResponse(
        id=a.id, title=a.title, meta_title=a.meta_title,
        meta_description=a.meta_description, excerpt=a.excerpt,
        focus_keyword=a.focus_keyword, tags=_parse_tags(a.tags),
        content=a.content, seo_score=a.seo_score, word_count=a.word_count,
        status=a.status, scheduled_at=a.scheduled_at, published_at=a.published_at,
        wp_post_id=a.wp_post_id, wp_post_url=a.wp_post_url, created_at=a.created_at,
    )

def _to_list_item(a: Article) -> ArticleListItem:
    return ArticleListItem(
        id=a.id, title=a.title, focus_keyword=a.focus_keyword,
        seo_score=a.seo_score, word_count=a.word_count, status=a.status,
        scheduled_at=a.scheduled_at, published_at=a.published_at,
        target_site=a.target_site, created_at=a.created_at,
    )
