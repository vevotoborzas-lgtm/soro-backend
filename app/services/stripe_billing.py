from typing import Literal

import stripe

from app.core.config import Settings
from app.models.user import User

PlanId = Literal["starter", "pro", "agency"]


def configure_stripe(settings: Settings) -> None:
    stripe.api_key = settings.stripe_secret_key or ""


def price_id_for_plan(plan: PlanId, settings: Settings) -> str:
    return {
        "starter": settings.stripe_price_starter,
        "pro": settings.stripe_price_pro,
        "agency": settings.stripe_price_agency,
    }[plan]


def create_customer(email: str, user_id: str, settings: Settings) -> stripe.Customer:
    configure_stripe(settings)
    return stripe.Customer.create(email=email, metadata={"user_id": user_id})


def create_checkout_session(
    user: User,
    plan: PlanId,
    settings: Settings,
) -> stripe.checkout.Session:
    configure_stripe(settings)
    price = price_id_for_plan(plan, settings)
    if not price:
        raise ValueError(f"Stripe price not configured for plan: {plan}")

    if not user.stripe_customer_id:
        cust = create_customer(user.email, user.id, settings)
        user.stripe_customer_id = cust.id

    sep = "&" if "?" in settings.billing_success_url else "?"
    success_url = f"{settings.billing_success_url}{sep}session_id={{CHECKOUT_SESSION_ID}}"

    return stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=success_url,
        cancel_url=settings.billing_cancel_url,
        client_reference_id=user.id,
        metadata={"user_id": user.id, "plan": plan},
        subscription_data={"metadata": {"user_id": user.id, "plan": plan}},
    )


def create_portal_session(user: User, settings: Settings) -> stripe.billing_portal.Session:
    configure_stripe(settings)
    if not user.stripe_customer_id:
        raise ValueError("No Stripe customer")
    return stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=settings.billing_portal_return_url,
    )


def normalize_subscription_status(status: str | None) -> str:
    if not status:
        return "none"
    if status in ("active", "trialing", "past_due", "canceled", "unpaid"):
        return status
    return "none"


def subscription_grants_access(status: str) -> bool:
    return status in ("active", "trialing")


def apply_subscription_to_user(user: User, sub: dict) -> None:
    user.stripe_subscription_id = sub["id"]
    user.subscription_status = normalize_subscription_status(sub.get("status"))
    md = sub.get("metadata") or {}
    if md.get("plan"):
        user.plan = str(md["plan"])
