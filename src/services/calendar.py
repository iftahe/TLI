import base64
import json
import logging
import os
from datetime import timedelta

from src.bot.utils import get_now

logger = logging.getLogger(__name__)


def get_calendar_service():
    """Build a Google Calendar API service using a service account.

    Reads GOOGLE_SERVICE_ACCOUNT_KEY env var (base64-encoded JSON).
    Returns a googleapiclient Resource or None on any failure.
    """
    key_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    if not key_b64.strip():
        return None

    try:
        key_json = base64.b64decode(key_b64)
        info = json.loads(key_json)

        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to build Google Calendar service: {e}", exc_info=True)
        return None


def get_calendar_map() -> dict:
    """Parse CALENDAR_MAP env var into {int_chat_id: calendar_id_string}.

    Format: "chat_id1:cal_id1,chat_id2:cal_id2"
    Returns empty dict on missing/invalid input.
    """
    raw = os.getenv("CALENDAR_MAP", "")
    if not raw.strip():
        return {}

    result = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        chat_id_str, cal_id = pair.split(":", 1)
        try:
            result[int(chat_id_str.strip())] = cal_id.strip()
        except ValueError:
            logger.warning(f"Invalid chat_id in CALENDAR_MAP: '{chat_id_str}'")
    return result


def get_tomorrow_events(service, calendar_id: str) -> list | None:
    """Fetch tomorrow's events from a Google Calendar.

    Returns list of {'time': 'HH:MM' or 'כל היום', 'title': str}
    or None on API error.
    """
    try:
        now = get_now()
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)

        time_min = tomorrow.isoformat()
        time_max = tomorrow_end.isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = []
        for item in events_result.get("items", []):
            title = item.get("summary", "(ללא כותרת)")
            start = item.get("start", {})

            if "dateTime" in start:
                from datetime import datetime
                dt = datetime.fromisoformat(start["dateTime"])
                time_str = dt.strftime("%H:%M")
            else:
                time_str = "כל היום"

            events.append({"time": time_str, "title": title})

        return events
    except Exception as e:
        logger.error(
            f"Failed to fetch events for calendar '{calendar_id}': {e}",
            exc_info=True,
        )
        return None


def format_events_section(events: list) -> str:
    """Format calendar events into a Hebrew text section."""
    if not events:
        return "📅 אין אירועים מחר — יום פתוח!"

    lines = ["📅 <b>אירועים מחר:</b>"]
    for ev in events:
        lines.append(f"  {ev['time']} — {ev['title']}")
    return "\n".join(lines)


def log_calendar_setup_status():
    """Log Google Calendar configuration status at startup."""
    key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    cal_map = os.getenv("CALENDAR_MAP", "")

    if key.strip() and cal_map.strip():
        n = len([p for p in cal_map.split(",") if ":" in p])
        logger.info(
            f"Google Calendar: service account key loaded, {n} calendar mapping(s) configured"
        )
    elif not key.strip():
        logger.info(
            "Google Calendar: GOOGLE_SERVICE_ACCOUNT_KEY not set — evening brief will skip calendar section.\n"
            "  Setup: (1) Create a GCP service account  (2) Enable Calendar API\n"
            "  (3) Base64-encode the JSON key: base64 -w0 service-account.json\n"
            "  (4) Set GOOGLE_SERVICE_ACCOUNT_KEY env var to the base64 string\n"
            "  (5) Share calendars with the service account email (read-only)\n"
            "  (6) Set CALENDAR_MAP=chat_id1:cal_id1,chat_id2:cal_id2"
        )
    else:
        logger.info(
            "Google Calendar: CALENDAR_MAP not set — evening brief will skip calendar section"
        )
