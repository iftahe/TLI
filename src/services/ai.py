import json
import logging

from src.bot.utils import get_now

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a smart personal assistant for the "The Life Itself" (TLI) task management bot.
You handle TWO types of user requests:
1. **TASK_CREATE** — The user wants to create a new task.
2. **TASK_QUERY** — The user is asking a question about their existing tasks.

Current date and time: {now} (Israel Time).

### Intent Classification:
- If the user asks a question (e.g., "כמה משימות יש לי?", "מה המשימות הדחופות?", "תסכם לי את העומס"), set intent to "TASK_QUERY".
- If the user wants to add/create a task (e.g., "לקנות חלב", "תזכיר לי מחר לשלם חשבון"), set intent to "TASK_CREATE".
- When in doubt, prefer "TASK_CREATE".

### TASK_QUERY Output Format:
Return JSON: {{"intent": "TASK_QUERY", "response": "Hebrew answer text here"}}
- Use the task list provided at the end of the user message to answer.
- Answer in Hebrew, concisely and helpfully.
- If no tasks are provided or the list is empty, say there are no pending tasks.

### TASK_CREATE — Hierarchy & Categories:
1. "home": General household tasks. Always set sub_category to "כללי".
2. "work": Professional/job tasks. Always set sub_category to "כללי".
3. "projects": Long-term or bureaucratic tasks. You MUST map these to one of the following sub_categories:
   - "משימות 📋" (General project tasks)
   - "בירוקרטיה 🏛️" (Legal, taxes, government, bills, insurance)
   - "קניות 🛒" (Project-related shopping)

### TASK_CREATE — Priority Logic:
- If the user uses words like "דחוף" (urgent), "בהול", "קריטי", or "עכשיו", set priority to "urgent".
- Otherwise, always default to "normal".

### TASK_CREATE — Date & Time Handling:
- "מחר בבוקר" = tomorrow 09:00
- "מחר" (no time) = tomorrow 09:00
- "הערב" = today 20:00
- "עוד שעה" = 1 hour from now
- "יום [X]" = The next upcoming day X at 09:00.

### TASK_CREATE Output Format:
Return JSON with these fields:
- "intent": "TASK_CREATE"
- "text": string — the clean task description in Hebrew.
- "parent_category": "home", "work", or "projects".
- "sub_category": string — "כללי" for home/work, or the specific project sub-category.
- "priority": "urgent" or "normal".
- "reminder_time": ISO 8601 datetime string (YYYY-MM-DDTHH:MM:SS) or null.

### Examples:
- "תזכיר לי מחר לקנות חלב דחוף"
  -> {{"intent": "TASK_CREATE", "text": "לקנות חלב", "parent_category": "home", "sub_category": "כללי", "priority": "urgent", "reminder_time": "2026-02-19T09:00:00"}}

- "להוסיף לפרויקטים לשלם ארנונה"
  -> {{"intent": "TASK_CREATE", "text": "לשלם ארנונה", "parent_category": "projects", "sub_category": "בירוקרטיה 🏛️", "priority": "normal", "reminder_time": null}}

- "כמה משימות דחופות יש לי?"
  -> {{"intent": "TASK_QUERY", "response": "יש לך 3 משימות דחופות: ..."}}

- "מה יש לי לעשות היום?"
  -> {{"intent": "TASK_QUERY", "response": "היום יש לך 5 משימות פתוחות: ..."}}
"""


_CATEGORY_LABELS_HE = {"home": "בית", "work": "עבודה", "projects": "פרויקטים"}
_PRIORITY_LABELS_HE = {"urgent": "דחוף", "normal": "רגיל", "low": "נמוך"}


def _build_task_context(chat_id: int) -> str:
    """Build a text summary of the user's pending tasks for AI context.

    Returns empty string on any error (graceful degradation).
    """
    try:
        from src.database.core import SessionLocal
        from src.database.models import Task
        from src.bot.utils import get_accessible_filter
    except ImportError:
        logger.warning("Could not import DB modules for task context")
        return ""

    session = SessionLocal()
    try:
        tasks = (
            session.query(Task)
            .filter(get_accessible_filter(chat_id), Task.status == "pending")
            .order_by(Task.created_at.desc())
            .limit(50)
            .all()
        )
        if not tasks:
            return "\n\n--- המשימות הנוכחיות שלך ---\nאין משימות פתוחות."

        lines = ["\n\n--- המשימות הנוכחיות שלך ---"]
        for i, t in enumerate(tasks, 1):
            cat = _CATEGORY_LABELS_HE.get(t.parent_category, t.parent_category)
            pri = _PRIORITY_LABELS_HE.get(t.priority, t.priority)
            line = f"{i}. [{cat}] ({pri}) {t.text}"
            if t.sub_category and t.sub_category != "כללי":
                line += f" | תת-קטגוריה: {t.sub_category}"
            if t.reminder_time:
                line += f" | תזכורת: {t.reminder_time.strftime('%d/%m %H:%M')}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Failed to build task context: {e}", exc_info=True)
        return ""
    finally:
        session.close()


def _validate_query_response(data: dict) -> str | None:
    """Validate and extract a TASK_QUERY response from Gemini output."""
    response = data.get("response")
    if response and isinstance(response, str) and response.strip():
        return response.strip()
    return None


def _validate_parsed_data(data: dict) -> dict | None:
    """Validate and sanitize Gemini-parsed task data."""
    now = get_now()
    result = {}

    desc = data.get("text") or data.get("description")
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
    elif result["parent_category"] == "projects":
        result["sub_category"] = "משימות 📋"
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


def parse_task_from_text(text: str, api_key: str, chat_id: int = None) -> dict | None:
    """Parse free-form Hebrew text into structured task data or answer a query.

    Returns dict with either:
    - intent=TASK_CREATE + description, parent_category, priority, sub_category, reminder_time
    - intent=TASK_QUERY + response (Hebrew answer text)
    - None on any failure.
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

        user_message = text
        if chat_id is not None:
            task_context = _build_task_context(chat_id)
            if task_context:
                user_message = text + task_context

        response = model.generate_content(
            user_message,
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

    intent = data.get("intent", "TASK_CREATE")

    if intent == "TASK_QUERY":
        response_text = _validate_query_response(data)
        if response_text:
            return {"intent": "TASK_QUERY", "response": response_text}
        return None

    result = _validate_parsed_data(data)
    if result:
        result["intent"] = "TASK_CREATE"
    return result


def parse_task_from_voice(audio_path: str, api_key: str, mime_type: str = "audio/ogg", chat_id: int = None) -> dict | None:
    """Parse a voice message into structured task data or answer a query.

    Uploads the audio file to Gemini, transcribes and parses it.
    Returns dict with either:
    - intent=TASK_CREATE + description, parent_category, priority, sub_category, reminder_time
    - intent=TASK_QUERY + response (Hebrew answer text)
    - None on any failure.
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

        voice_prompt = "תמלל את ההודעה הקולית וזהה אם המשתמש רוצה ליצור משימה או לשאול שאלה על המשימות שלו."
        if chat_id is not None:
            task_context = _build_task_context(chat_id)
            if task_context:
                voice_prompt += task_context

        response = model.generate_content(
            [uploaded_file, voice_prompt],
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

    intent = data.get("intent", "TASK_CREATE")

    if intent == "TASK_QUERY":
        response_text = _validate_query_response(data)
        if response_text:
            return {"intent": "TASK_QUERY", "response": response_text}
        return None

    result = _validate_parsed_data(data)
    if result:
        result["intent"] = "TASK_CREATE"
    return result
