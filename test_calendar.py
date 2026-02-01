"""CLI diagnostic script to verify Google Calendar integration independently.

Usage:
    python test_calendar.py

Requires GOOGLE_SERVICE_ACCOUNT_KEY and CALENDAR_MAP env vars (from .env).
"""
import os
import sys
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("test_calendar")


def main():
    # --- Step 1: Check env vars ---
    key_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    cal_map_raw = os.getenv("CALENDAR_MAP", "")

    print("\n=== Step 1: Environment Variables ===")
    if not key_b64.strip():
        print("FAIL: GOOGLE_SERVICE_ACCOUNT_KEY is empty or not set.")
        sys.exit(1)
    print(f"OK: GOOGLE_SERVICE_ACCOUNT_KEY is set ({len(key_b64)} chars)")

    if not cal_map_raw.strip():
        print("WARN: CALENDAR_MAP is empty — will test service auth only, no event fetch.")
    else:
        print(f"OK: CALENDAR_MAP = {cal_map_raw}")

    # --- Step 2: Decode key ---
    print("\n=== Step 2: Decode Service Account Key ===")
    import base64, json
    try:
        key_json = base64.b64decode(key_b64)
        info = json.loads(key_json)
    except Exception as e:
        print(f"FAIL: Cannot decode/parse key: {e}")
        sys.exit(1)

    sa_email = info.get("client_email", "???")
    project = info.get("project_id", "???")
    print(f"OK: project_id={project}, client_email={sa_email}")

    # --- Step 3: Build service ---
    print("\n=== Step 3: Build Google Calendar Service ===")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        service = build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"FAIL: Cannot build service: {e}")
        sys.exit(1)
    print("OK: Service built successfully")

    # --- Step 4: Parse CALENDAR_MAP ---
    print("\n=== Step 4: Parse CALENDAR_MAP ===")
    from src.services.calendar import get_calendar_map
    cal_map = get_calendar_map()
    if not cal_map:
        print("WARN: No mappings parsed. Set CALENDAR_MAP=chat_id:calendar_id")
        print("Attempting calendarList.list() to show available calendars...")
        try:
            result = service.calendarList().list().execute()
            for cal in result.get("items", []):
                print(f"  - {cal['id']}  ({cal.get('summary', '?')})")
        except Exception as e:
            print(f"  FAIL: calendarList.list() error: {e}")
        sys.exit(0)

    for chat_id, cal_id in cal_map.items():
        print(f"  chat_id={chat_id} -> calendar_id={cal_id}")

    # --- Step 5: Fetch tomorrow's events ---
    print("\n=== Step 5: Fetch Tomorrow's Events ===")
    from src.services.calendar import get_tomorrow_events, format_events_section
    from src.bot.utils import get_now
    from datetime import timedelta

    now = get_now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"Now (Israel): {now.isoformat()}")
    print(f"Tomorrow range: {tomorrow.isoformat()} -> {tomorrow.replace(hour=23, minute=59, second=59).isoformat()}")

    for chat_id, cal_id in cal_map.items():
        print(f"\n--- Calendar: {cal_id} (chat {chat_id}) ---")
        events = get_tomorrow_events(service, cal_id)
        if events is None:
            print("FAIL: get_tomorrow_events returned None (check logs above)")
        elif len(events) == 0:
            print("OK: No events tomorrow (empty list)")
        else:
            print(f"OK: {len(events)} event(s) found:")
            print(format_events_section(events))

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
