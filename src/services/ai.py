import json
import logging

from src.bot.utils import get_now

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a Hebrew task parser. Extract structured task data from free-form Hebrew text.

Current date and time: {now}

Return ONLY valid JSON with these fields:
- "description": string — the task description in Hebrew (clean, concise)
- "parent_category": "home", "work", or "projects" — default "home" if unclear
- "priority": "urgent", "normal", or "low" — default "normal" if unclear
- "sub_category": string or null — for "projects" category only, one of: "משימות 📋", "בירוקרטיה 🏛️", "קניות 🛒". Set null for home/work.
- "reminder_time": ISO 8601 datetime string (e.g. "2026-02-19T09:00:00") or null if no time mentioned

Rules:
- "מחר בבוקר" = tomorrow 09:00
- "מחר" without time = tomorrow 09:00
- "הערב" = today 20:00
- "עוד שעה" = 1 hour from now
- "עוד 3 ימים" = 3 days from now at 09:00
- "דחוף" or "בדחיפות" or "urgent" = priority "urgent"
- Work keywords (פגישה, לקוח, משרד, פרויקט, דוח, עבודה) → "work"
- Project keywords (ביטוח, חשבון, עו"ד, משכנתא, רשות, עירייה, טאבו, מס, דרכון, בירוקרטיה, ויזה, רישום) → "projects"
- Home keywords (קניות, בית, ניקיון, תיקון, סידור, כביסה) → "home"
- For "projects", map to the most fitting sub_category
- If no time reference, set reminder_time to null
- Return ONLY the JSON object, no markdown, no explanation
"""


def _validate_parsed_data(data: dict) -> dict | None:
    """Validate and sanitize Gemini-parsed task data."""
    now = get_now()
    result = {}

    desc = data.get("description")
    if not desc or not isinstance(desc, str):
        logger.warning("Gemini returned no description")
        return None
    result["description"] = desc.strip()

    cat = data.get("parent_category", "home")
    result["parent_category"] = cat if cat in ("home", "work", "projects") else "home"

    pri = data.get("priority", "normal")
    result["priority"] = pri if pri in ("urgent", "normal", "low") else "normal"

    # Sub-category: only meaningful for projects
    sub_cat = data.get("sub_category")
    if result["parent_category"] == "projects" and sub_cat and isinstance(sub_cat, str):
        result["sub_category"] = sub_cat.strip()
    else:
        result["sub_category"] = "כללי"

    reminder_raw = data.get("reminder_time")
    if reminder_raw and isinstance(reminder_raw, str):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(reminder_raw)
            now_naive = now.replace(tzinfo=None)
            dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
            if dt_naive > now_naive:
                result["reminder_time"] = reminder_raw
            else:
                result["reminder_time"] = None
        except (ValueError, TypeError):
            result["reminder_time"] = None
    else:
        result["reminder_time"] = None

    return result


def parse_task_from_text(text: str, api_key: str) -> dict | None:
    """Parse free-form Hebrew text into structured task data using Gemini.

    Returns dict with description, parent_category, priority, sub_category, reminder_time
    or None on any failure.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai package not installed")
        return None

    try:
        genai.configure(api_key=api_key)

        now = get_now()
        system = _SYSTEM_PROMPT.format(now=now.strftime("%Y-%m-%d %H:%M:%S"))

        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system,
        )

        response = model.generate_content(
            text,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
            request_options={"timeout": 15},
        )

        raw = response.text.strip()
        logger.info(f"Gemini raw response: {raw[:200]}")
        data = json.loads(raw)
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}", exc_info=True)
        return None

    return _validate_parsed_data(data)


def parse_task_from_voice(audio_path: str, api_key: str, mime_type: str = "audio/ogg") -> dict | None:
    """Parse a voice message into structured task data using Gemini.

    Uploads the audio file to Gemini, transcribes and parses it.
    Returns dict with description, parent_category, priority, sub_category, reminder_time
    or None on any failure.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai package not installed")
        return None

    try:
        genai.configure(api_key=api_key)

        uploaded_file = genai.upload_file(audio_path, mime_type=mime_type)
        logger.info(f"Uploaded voice file: {uploaded_file.name}")

        now = get_now()
        system = _SYSTEM_PROMPT.format(now=now.strftime("%Y-%m-%d %H:%M:%S"))

        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system,
        )

        response = model.generate_content(
            [uploaded_file, "תמלל את ההודעה הקולית וחלץ ממנה משימה מובנית."],
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
            request_options={"timeout": 30},
        )

        raw = response.text.strip()
        logger.info(f"Gemini voice response: {raw[:200]}")
        data = json.loads(raw)
    except Exception as e:
        logger.error(f"Gemini voice API call failed: {e}", exc_info=True)
        return None

    return _validate_parsed_data(data)
