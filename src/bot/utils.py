import os
from datetime import datetime, timezone
import zoneinfo

ISRAEL_TZ = zoneinfo.ZoneInfo("Asia/Jerusalem")

def get_now() -> datetime:
    """Returns the current time in Israel timezone."""
    return datetime.now(ISRAEL_TZ)

def to_naive_israel(dt: datetime) -> datetime:
    """Converts a timezone-aware datetime to a naive datetime in Israel time (for DB storage)."""
    if dt.tzinfo is None:
        return dt # Assume already naive
    return dt.astimezone(ISRAEL_TZ).replace(tzinfo=None)

def _load_allowed_users():
    raw = os.getenv("ALLOWED_USERS", "")
    if not raw.strip():
        return None  # None means no restriction (backwards compatible)
    return set(int(uid.strip()) for uid in raw.split(",") if uid.strip())

ALLOWED_USERS = _load_allowed_users()

def is_user_allowed(user_id: int) -> bool:
    """Returns True if the user is in the whitelist, or if no whitelist is configured."""
    if ALLOWED_USERS is None:
        return True
    return user_id in ALLOWED_USERS
