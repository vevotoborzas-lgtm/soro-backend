from datetime import datetime, timezone

from app.core.config import Settings
from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc_aware(dt: datetime | None) -> datetime | None:
    """Normalize DB/driver datetimes so comparisons never mix naive and aware values."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def trial_ends_at_utc(user: User) -> datetime:
    """Trial end instant in UTC (aware). Safe for APIs and subscription checks."""
    end = as_utc_aware(user.trial_ends_at)
    return end if end is not None else utc_now()


def sync_monthly_article_counter(user: User) -> None:
    """Reset monthly counter when calendar month changes; init legacy rows without wiping counts."""
    month_key = utc_now().strftime("%Y-%m")
    if not user.articles_quota_month:
        user.articles_quota_month = month_key
        return
    if user.articles_quota_month != month_key:
        user.articles_used_this_month = 0
        user.articles_quota_month = month_key


def has_active_access(user: User) -> bool:
    if user.subscription_status in ("active", "trialing"):
        return True
    return utc_now() < trial_ends_at_utc(user)


def monthly_quota_for_user(user: User, settings: Settings) -> int:
    if user.subscription_status in ("active", "trialing"):
        key = (user.plan or "pro").lower()
        if key == "starter":
            return settings.quota_starter
        if key == "agency":
            return settings.quota_agency
        return settings.quota_pro
    if utc_now() < trial_ends_at_utc(user):
        return settings.quota_trial
    return 0
