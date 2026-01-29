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
