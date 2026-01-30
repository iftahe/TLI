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

def get_accessible_filter(chat_id):
    """Returns a SQLAlchemy filter for tasks accessible to a user:
    own tasks OR shared Home tasks."""
    from sqlalchemy import or_, and_
    from src.database.models import Task
    return or_(
        Task.chat_id == chat_id,
        and_(Task.is_shared == 1, Task.parent_category == 'home')
    )

def get_accessible_task(session, task_id, chat_id):
    """Fetches a task by ID if the user owns it or it's a shared Home task.
    Returns the task or None."""
    from sqlalchemy import or_, and_
    from src.database.models import Task
    return session.query(Task).filter(
        Task.id == task_id,
        or_(
            Task.chat_id == chat_id,
            and_(Task.is_shared == 1, Task.parent_category == 'home')
        )
    ).first()
