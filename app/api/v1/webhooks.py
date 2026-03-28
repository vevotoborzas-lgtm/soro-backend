"""
app/api/v1/webhooks.py – WordPress publish webhook
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import hmac, hashlib, json

from app.core.database import get_db
from app.core.config import settings
from app.models.article import Article

router = APIRouter()


class PublishWebhookPayload(BaseModel):
    article_id:  str
    wp_post_id:  int
    url:         str
    site_url:    str
    event:       str = "published"


@router.post("/publish-confirm")
async def publish_confirm_webhook(
    payload: PublishWebhookPayload,
    x_soro_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    A WordPress plugin hívja ezt, amikor sikeresen publikálta a cikket.
    """
    # Aláírás ellenőrzés (HMAC-SHA256)
    if x_soro_signature and settings.SECRET_KEY:
        expected = hmac.new(
            settings.SECRET_KEY.encode(),
            json.dumps(payload.model_dump(), sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(x_soro_signature, expected):
            raise HTTPException(status_code=401, detail="Érvénytelen aláírás")

    result = await db.execute(
        select(Article).where(Article.id == payload.article_id)
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Cikk nem található")

    from datetime import datetime, timezone
    article.status      = "published"
    article.wp_post_id  = payload.wp_post_id
    article.wp_post_url = payload.url
    article.published_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "OK", "article_id": payload.article_id}
