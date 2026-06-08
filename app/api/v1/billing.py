from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.services import stripe_billing

router = APIRouter(prefix="/v1/billing", tags=["billing"])
settings = get_settings()

PlanId = Literal["starter", "pro", "agency"]


class CheckoutIn(BaseModel):
    plan: PlanId = "pro"


@router.post("/checkout-session")
async def create_checkout(
    payload: CheckoutIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing not configured")
    try:
        session = stripe_billing.create_checkout_session(user, payload.plan, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc
    await db.commit()
    return {"url": session.url, "id": session.id}


@router.post("/portal-session")
async def create_portal(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing not configured")
    try:
        session = stripe_billing.create_portal_session(user, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc
    await db.commit()
    return {"url": session.url}
