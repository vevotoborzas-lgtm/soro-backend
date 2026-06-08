import logging

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from stripe.error import SignatureVerificationError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_hmac_signature
from app.models.user import User
from app.services.stripe_billing import apply_subscription_to_user, configure_stripe


router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
settings = get_settings()
log = logging.getLogger("soro.webhooks")


class PublishConfirmPayload(BaseModel):
    article_id: str
    wp_post_id: str | None = None
    wp_post_url: str | None = None
    status: str = "published"


@router.post("/publish-confirm")
async def publish_confirm(
    request: Request,
    payload: PublishConfirmPayload,
    x_soro_signature: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
):
    sig = x_soro_signature or x_signature
    if not sig:
        raise HTTPException(status_code=401, detail="Missing signature header")
    body = await request.body()
    if not verify_hmac_signature(body, sig, settings.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    return {"ok": True, "article_id": payload.article_id, "status": payload.status}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="Missing stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid payload") from exc
    except SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    et = event["type"]
    data = event["data"]["object"]

    if et == "checkout.session.completed":
        if data.get("mode") != "subscription":
            return {"received": True}
        user_id = data.get("client_reference_id") or (data.get("metadata") or {}).get("user_id")
        sub_id = data.get("subscription")
        if not user_id or not sub_id:
            return {"received": True}
        if not settings.stripe_secret_key:
            return {"received": True}
        configure_stripe(settings)
        sub_obj = stripe.Subscription.retrieve(sub_id)
        sub = sub_obj.to_dict() if hasattr(sub_obj, "to_dict") else sub_obj
        res = await db.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()
        if user:
            apply_subscription_to_user(user, sub)
            plan = (data.get("metadata") or {}).get("plan")
            if plan:
                user.plan = str(plan)
            cust = data.get("customer")
            if cust and not user.stripe_customer_id:
                user.stripe_customer_id = cust
            await db.commit()
            log.info(
                "stripe checkout applied user_id=%s subscription_id=%s plan=%s status=%s",
                user_id,
                sub_id,
                user.plan,
                user.subscription_status,
            )
        else:
            log.warning("stripe checkout no user user_id=%s subscription_id=%s", user_id, sub_id)
        return {"received": True}

    if et in ("customer.subscription.updated", "customer.subscription.created"):
        sub = data
        user_id = (sub.get("metadata") or {}).get("user_id")
        user = None
        if user_id:
            res = await db.execute(select(User).where(User.id == user_id))
            user = res.scalar_one_or_none()
        if not user:
            cid = sub.get("customer")
            if cid:
                res = await db.execute(select(User).where(User.stripe_customer_id == cid))
                user = res.scalar_one_or_none()
        if user:
            apply_subscription_to_user(user, sub)
            await db.commit()
            log.info(
                "stripe subscription event=%s user_id=%s subscription_id=%s status=%s",
                et,
                user.id,
                user.stripe_subscription_id,
                user.subscription_status,
            )
        return {"received": True}

    if et == "customer.subscription.deleted":
        sub = data
        res = await db.execute(select(User).where(User.stripe_subscription_id == sub.get("id")))
        user = res.scalar_one_or_none()
        if user:
            user.subscription_status = "canceled"
            user.stripe_subscription_id = None
            await db.commit()
        return {"received": True}

    return {"received": True}
