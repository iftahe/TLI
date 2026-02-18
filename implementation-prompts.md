# Implementation Prompts — TLI Bot Evolution

Copy each prompt to a fresh Claude Code session. Each phase is self-contained.
Run them **in order** — each phase depends on the previous one being complete.

---

## PROMPT 1: Phase 1 — Archive Legacy Features

```
We are refactoring the TLI Telegram bot. This is Phase 1: Archive Legacy Features.

The project is at the current working directory. Read the CLAUDE.md for full context.

**What to do:**

1. **Create `archive/` directory** at project root with 3 files:

   a. `archive/weather.py` — copy the ENTIRE contents of `src/services/weather.py` verbatim.

   b. `archive/calendar.py` — copy the ENTIRE contents of `src/services/calendar.py` verbatim.

   c. `archive/jobs_archived.py` — Read `src/scheduler/jobs.py` and move these functions/constants to the archive file (with all their imports):
      - `_BRIEFING_HOOKS` dict
      - `_get_briefing_hook()` function
      - `_age_indicator()` function
      - `_format_task_line()` function
      - `_EVENING_HOOKS` dict
      - `_get_evening_reflection()` function
      - `daily_briefing_job()` function
      - `evening_brief_job()` function
      Add a comment at the top: `# Archived briefing/weather/calendar functions — disabled in refactor`

2. **Clean `src/scheduler/jobs.py`** — After moving the archived functions, this file should ONLY contain:
   - `send_message_async()` function
   - `send_reminder_job()` function
   - Their necessary imports (remove `random`, `timedelta`, and any weather/calendar/briefing-related imports)

3. **Clean `src/scheduler/service.py`**:
   - Remove the `add_daily_briefing_job()` function entirely
   - Remove the `add_evening_brief_job()` function entirely
   - Update `_STALE_JOB_IDS` to include the old briefing job IDs:
     ```python
     _STALE_JOB_IDS = ['daily_summary', 'daily_briefing', 'evening_brief']
     ```
   This ensures APScheduler cleans these ghost jobs from the persistent store on next startup (prevents LookupError crash).

4. **Clean `main.py`**:
   - Remove `add_daily_briefing_job, add_evening_brief_job` from the import on line 9 (keep `start_scheduler` and `recover_missed_reminders`)
   - Remove the calls `add_daily_briefing_job()` and `add_evening_brief_job()` (lines 71-72)
   - Remove `from src.services.calendar import log_calendar_setup_status` and the call `log_calendar_setup_status()` (lines 75-76)
   - Remove the OpenWeatherMap API key check block (lines 78-82)
   - KEEP the Gemini API key check (lines 84-88)

5. **Delete the original service files**:
   - Delete `src/services/weather.py`
   - Delete `src/services/calendar.py`
   - Keep `src/services/__init__.py` and `src/services/ai.py`

6. **Clean `requirements.txt`**:
   - First, grep the codebase (excluding `archive/`) to verify `requests`, `google-api-python-client`, and `google-auth` are not used anywhere else
   - If safe, remove these 3 packages from `requirements.txt`
   - Keep `google-generativeai` (used by AI service)

**Code standards:**
- Always use SessionLocal with try/except/finally and explicit rollback()/close()
- Do NOT modify any handler files or AI files in this phase

After completing all steps, run `python -c "from src.scheduler.service import start_scheduler; from src.scheduler.jobs import send_reminder_job; print('Phase 1 imports OK')"` to verify no import errors.
```

---

## PROMPT 2: Phase 2 — Database & Constants

```
We are refactoring the TLI Telegram bot. This is Phase 2: Database & Constants.
Phase 1 (archiving legacy features) is already complete.

The project is at the current working directory. Read the CLAUDE.md for full context.

**What to do:**

1. **`src/bot/constants.py`** — Add a new category constant:
   ```python
   CATEGORY_PROJECTS = 'projects'
   ```
   Add it alongside the existing `CATEGORY_HOME = 'home'` and `CATEGORY_WORK = 'work'`.

2. **`src/database/core.py`** — Two changes:

   a. Add project subcategories to the `DEFAULT_CATEGORIES` list:
   ```python
   # Projects
   ("משימות 📋", "projects"),
   ("בירוקרטיה 🏛️", "projects"),
   ("קניות 🛒", "projects"),
   ```

   b. Add a new function `ensure_project_categories(session, chat_id)` that seeds project subcategories for existing users who already have home/work categories. Pattern:
   ```python
   def ensure_project_categories(session, chat_id: int):
       """Seeds project subcategories for a user if they have none yet."""
       count = session.query(SubCategory).filter(
           SubCategory.chat_id == chat_id,
           SubCategory.parent == 'projects'
       ).count()
       if count == 0:
           project_cats = [
               SubCategory(name=name, parent=parent, chat_id=chat_id, is_active=1)
               for name, parent in DEFAULT_CATEGORIES
               if parent == 'projects'
           ]
           session.add_all(project_cats)
           session.commit()
   ```

3. **`src/database/models.py`** — Update the inline comments on `parent_category` and `parent` columns to reflect the new valid value:
   - Task.parent_category: `# 'home', 'work', or 'projects'`
   - SubCategory.parent: `# 'home', 'work', or 'projects'`
   No actual schema changes needed — these are plain String columns.

**Important:** No schema migration is needed. The `parent_category` column on Task and `parent` column on SubCategory are plain VARCHAR/String columns with no database-level constraints. They accept any string value.

After completing all steps, run:
```
python -c "from src.bot.constants import CATEGORY_PROJECTS; from src.database.core import ensure_project_categories; print(f'Phase 2 OK: CATEGORY_PROJECTS={CATEGORY_PROJECTS}')"
```
```

---

## PROMPT 3: Phase 3 — Simplified Flow & New Handlers

```
We are refactoring the TLI Telegram bot. This is Phase 3: Simplified Manual Flow + New Handlers.
Phases 1-2 are already complete. `CATEGORY_PROJECTS = 'projects'` exists in constants.py.

The project is at the current working directory. Read the CLAUDE.md for full context.

**Context — Current vs New Flow:**
- Current home/work: Description -> Priority -> [Shared Choice for home] -> SubCategory -> Reminder
- NEW home/work: Description -> Reminder (defaults: priority='normal', sub_category='כללי', is_shared=0)
- NEW projects: Description -> SubCategory -> Reminder (defaults: priority='normal', is_shared=0)

**What to do:**

### A. `src/bot/handlers.py`

1. **`task_entry_handler()`** — Add `פרויקטים` prefix and change flow branching:
   - Add detection for text starting with `פרויקטים` (set parent=CATEGORY_PROJECTS, rest=text[8:].strip() since len('פרויקטים')=8)
   - When description exists (rest is not empty):
     - For `CATEGORY_PROJECTS`: show subcategory keyboard (`get_subcategory_keyboard(parent, chat_id=...)`), return `SUB_CATEGORY`
     - For `CATEGORY_HOME` / `CATEGORY_WORK`: show reminder keyboard (`get_reminder_keyboard()`), return `REMINDER`
   - When no description: ask "מה המשימה?", return `DESCRIPTION` (unchanged)
   - Import `CATEGORY_PROJECTS` from constants

2. **`description_handler()`** — Same branching after capturing description:
   - For projects: show subcategory keyboard, return `SUB_CATEGORY`
   - For home/work: show reminder keyboard, return `REMINDER`

3. **`reminder_callback()`** — Update task creation to use defaults:
   - Change `context.user_data['priority']` to `context.user_data.get('priority', 'normal')`
   - Change `context.user_data['subcategory']` to `context.user_data.get('subcategory', 'כללי')`
   - Hardcode `is_shared = 0` (remove the `context.user_data.get('is_shared')` logic)

4. **`custom_reminder_handler()`** — Same default changes:
   - `context.user_data.get('priority', 'normal')`
   - `context.user_data.get('subcategory', 'כללי')`
   - Hardcode `is_shared = 0`

5. **`list_tasks_command()`** — Exclude projects from main list:
   - Add `Task.parent_category != 'projects'` to the query filter

6. **Add `filter_today_callback()`** — New handler for "Today" dashboard button:
   ```python
   async def filter_today_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
       query = update.callback_query
       await query.answer()
       session = SessionLocal()
       try:
           chat_id = update.effective_chat.id
           now = get_now()
           now_naive = now.replace(tzinfo=None)
           today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
           today_end = now_naive.replace(hour=23, minute=59, second=59)

           tasks = session.query(Task).filter(
               get_accessible_filter(chat_id),
               Task.status == 'pending',
               Task.parent_category != 'projects',
               Task.reminder_time != None,
               Task.reminder_time >= today_start,
               Task.reminder_time <= today_end,
           ).order_by(Task.reminder_time).all()

           if not tasks:
               text_lines = ["📌 <b>היום</b> — אין משימות מתוזמנות להיום"]
           else:
               text_lines = [f"📌 <b>משימות להיום</b> — {len(tasks)} משימות\n"]

           buttons = []
           for i, t in enumerate(tasks, 1):
               t_str = t.reminder_time.strftime("%H:%M") if t.reminder_time else ""
               cat = "🏠" if t.parent_category == CATEGORY_HOME else "💼"
               p_icon = "🔴" if t.priority == 'urgent' else "🟡" if t.priority == 'normal' else "🟢"
               text_lines.append(f"  {i}. {t_str} {cat} {t.text} {p_icon}")
               btn_label = f"{i}. {t.text[:25]}"
               buttons.append(InlineKeyboardButton(btn_label, callback_data=f"{VIEW_TASK}{t.id}"))

           keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
           keyboard.append([InlineKeyboardButton("🔙 חזרה לראשי", callback_data="back_to_dashboard")])

           msg = "\n".join(text_lines)
           await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
       except Exception as e:
           session.rollback()
           logger.error(f"Error filtering today tasks: {e}")
           await query.edit_message_text("❌ שגיאה בטעינת משימות היום.")
       finally:
           session.close()
   ```

7. **Add `filter_projects_callback()`** — New handler for "Projects" dashboard button:
   ```python
   async def filter_projects_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
       query = update.callback_query
       await query.answer()
       session = SessionLocal()
       try:
           chat_id = update.effective_chat.id
           tasks = session.query(Task).filter(
               Task.chat_id == chat_id,
               Task.status == 'pending',
               Task.parent_category == 'projects'
           ).all()

           priority_order = {'urgent': 0, 'normal': 1, 'low': 2}
           tasks.sort(key=lambda t: priority_order.get(t.priority, 99))

           grouped = {}
           for t in tasks:
               sub = t.sub_category or "כללי"
               grouped.setdefault(sub, []).append(t)

           if not tasks:
               text_lines = ["📁 <b>פרויקטים</b> — אין משימות"]
           else:
               text_lines = [f"📁 <b>פרויקטים</b> — {len(tasks)} משימות\n"]

           buttons = []
           num = 0
           for sub_name, section_tasks in grouped.items():
               text_lines.append(f"<b>{sub_name}</b>")
               for t in section_tasks:
                   num += 1
                   p_icon = "🔴" if t.priority == 'urgent' else "🟡" if t.priority == 'normal' else "🟢"
                   text_lines.append(f"  {num}. {t.text} {p_icon}")
                   btn_label = f"{num}. {t.text[:25]}"
                   buttons.append(InlineKeyboardButton(btn_label, callback_data=f"{VIEW_TASK}{t.id}"))
               text_lines.append("")

           keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
           keyboard.append([InlineKeyboardButton("🔙 חזרה לראשי", callback_data="back_to_dashboard")])

           msg = "\n".join(text_lines)
           await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
       except Exception as e:
           session.rollback()
           logger.error(f"Error filtering projects: {e}")
           await query.edit_message_text("❌ שגיאה בטעינת הפרויקטים.")
       finally:
           session.close()
   ```

### B. `src/bot/bot_app.py`

1. **Update main conversation handler** (line 57-68):
   - Change entry regex to: `r'^(בית|עבודה|פרויקטים)'`
   - Remove `PRIORITY` state from states dict (line 61)
   - Remove `SHARED_CHOICE` state from states dict (line 62)
   - Keep `DESCRIPTION`, `SUB_CATEGORY`, `REMINDER`, `WAITING_CUSTOM_REMINDER`

2. **Remove** the import `from src.bot.handlers import shared_choice_callback` (line 7)

3. **Register new callback handlers** — add after line 118 (near the other dashboard navigation handlers):
   ```python
   app.add_handler(CallbackQueryHandler(filter_today_callback, pattern="^filter_today$"))
   app.add_handler(CallbackQueryHandler(filter_projects_callback, pattern="^filter_projects$"))
   ```
   Import these from `src.bot.handlers` (they're imported via the `from src.bot.handlers import *` on line 5).

**Code standards:**
- Always use SessionLocal with try/except/finally and explicit rollback()/close()
- Use get_now() for all datetime operations
- Keep all UI strings in Hebrew
- Use `from src.bot.constants import CATEGORY_PROJECTS` where needed

After completing, verify no import errors:
```
python -c "from src.bot.bot_app import create_app; print('Phase 3 imports OK')"
```
```

---

## PROMPT 4: Phase 4 — Dashboard Update

```
We are refactoring the TLI Telegram bot. This is Phase 4: Dashboard Redesign.
Phases 1-3 are complete. `CATEGORY_PROJECTS` exists, new filter handlers exist.

The project is at the current working directory. Read the CLAUDE.md for full context.

**What to do:**

### `src/bot/dashboard_handlers.py` — Rewrite `dashboard_command()`

Read the current file first, then rewrite `dashboard_command()` with these changes:

1. **Add imports**: `CATEGORY_PROJECTS` from constants

2. **Separate projects from main tasks**:
   ```python
   active_tasks = session.query(Task).filter(
       get_accessible_filter(chat_id),
       Task.status == 'pending'
   ).all()

   main_tasks = [t for t in active_tasks if t.parent_category != 'projects']
   project_tasks = [t for t in active_tasks if t.parent_category == 'projects']
   ```

3. **Calculate "Today" count** — tasks with reminder_time set for today (excluding projects):
   ```python
   now_naive = now.replace(tzinfo=None)
   today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
   today_end = now_naive.replace(hour=23, minute=59, second=59)

   today_tasks = [t for t in main_tasks
                  if t.reminder_time and today_start <= t.reminder_time <= today_end]
   today_count = len(today_tasks)
   ```

4. **Counts from main_tasks only** (not project_tasks):
   - `home_count` = home tasks
   - `work_count` = work tasks
   - `projects_count` = len(project_tasks)
   - `total` = len(main_tasks) (projects excluded from total)
   - `urgent_count` = urgent tasks in main_tasks

5. **Message layout**:
   ```
   👋 <b>{greeting} טוב!</b>
   📅 DD/MM

   📌 היום: N  ·  🏠 בית: N  ·  💼 עבודה: N
   סה״כ: N משימות פתוחות
   🔴 דחוף: N  (only if > 0)

   🔥 דחוף:  (only if urgent tasks exist, top 3, from main_tasks only)
     🏠/💼 task text

   🔔 תזכורות להיום:  (upcoming reminders from now to end of day)
     HH:MM — task text
   ```

6. **Keyboard** — 2 rows:
   ```python
   keyboard = [
       [
           InlineKeyboardButton(f"📌 היום ({today_count})", callback_data="filter_today"),
           InlineKeyboardButton(f"🏠 בית ({home_count})", callback_data="filter_home"),
           InlineKeyboardButton(f"💼 עבודה ({work_count})", callback_data="filter_work"),
       ],
       [
           InlineKeyboardButton(f"📁 פרויקטים ({projects_count})", callback_data="filter_projects"),
       ],
   ]
   ```

7. **Reminders section** — show upcoming (future) reminders from `main_tasks` only (not project tasks), from now to end of day.

8. **Keep** the existing pattern of handling both `update.message` and `update.callback_query` for the reply.

**Do NOT change** `quick_add_callback()` — it stays as-is.

**Code standards:**
- Use get_now() from src.bot.utils
- All UI strings in Hebrew
- HTML parse mode

After completing, verify:
```
python -c "from src.bot.dashboard_handlers import dashboard_command; print('Phase 4 OK')"
```
```

---

## PROMPT 5: Phase 5 — AI & Voice Integration

```
We are refactoring the TLI Telegram bot. This is Phase 5: AI & Voice Integration.
Phases 1-4 are complete. The bot has a new `projects` category with subcategories.

The project is at the current working directory. Read the CLAUDE.md for full context.

**IMPORTANT CONTEXT:**
- The project uses `google-generativeai` (legacy SDK), NOT the new `google-genai` SDK
- Gemini system prompt MUST be passed via `system_instruction` param in `GenerativeModel()` constructor
- The bot uses `python-telegram-bot` with `job-queue` and `callback-data` extras

**What to do:**

### A. `src/services/ai.py` — Update prompt, add voice, refactor validation

Read the current file first.

1. **Update `_SYSTEM_PROMPT`** — Replace with:
   ```python
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
   ```

2. **Extract `_validate_parsed_data(data)` helper** — Take the validation block from `parse_task_from_text()` and make it a standalone function:
   ```python
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
   ```

3. **Update `parse_task_from_text()`** — Replace the inline validation with:
   ```python
   return _validate_parsed_data(data)
   ```

4. **Add `parse_task_from_voice()` function**:
   ```python
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
   ```

### B. `src/bot/ai_handlers.py` — Voice handler & confirmation refactor

Read the current file first.

1. **Update `_CATEGORY_LABELS`**:
   ```python
   _CATEGORY_LABELS = {"home": "🏠 בית", "work": "💼 עבודה", "projects": "📁 פרויקטים"}
   ```

2. **Add imports** at top:
   ```python
   import tempfile
   ```

3. **Extract `_show_ai_confirmation()` helper** — Pull the confirmation message building from `_process_ai_text()` into a shared function:
   ```python
   async def _show_ai_confirmation(message, result):
       """Build and show AI task confirmation message with Save/Cancel buttons."""
       pri_label = _PRIORITY_LABELS.get(result["priority"], result["priority"])
       cat_label = _CATEGORY_LABELS.get(result["parent_category"], result["parent_category"])

       if result["reminder_time"]:
           try:
               dt = datetime.fromisoformat(result["reminder_time"])
               time_str = dt.strftime("%H:%M %d/%m")
           except ValueError:
               time_str = "ללא"
       else:
           time_str = "ללא"

       sub_cat = result.get("sub_category", "כללי")

       msg = (
           f"🤖 <b>אישור משימה מ-AI</b>\n\n"
           f"📝 {result['description']}\n"
           f"📂 {cat_label}"
       )
       if result["parent_category"] == "projects" and sub_cat != "כללי":
           msg += f" > {sub_cat}"
       msg += f"\n⚡ {pri_label}\n"
       msg += f"⏰ תזכורת: {time_str}\n\n"
       msg += "לשמור את המשימה?"

       keyboard = [
           [
               InlineKeyboardButton("✅ שמור", callback_data=AI_CONFIRM_SAVE),
               InlineKeyboardButton("❌ בטל", callback_data=AI_CONFIRM_CANCEL),
           ]
       ]

       await message.edit_text(
           msg,
           reply_markup=InlineKeyboardMarkup(keyboard),
           parse_mode="HTML",
       )
   ```

4. **Update `_process_ai_text()`** — Replace the inline confirmation message building with:
   ```python
   context.user_data["ai_task"] = result
   await _show_ai_confirmation(processing_msg, result)
   return AI_CONFIRM
   ```

5. **Add `voice_handler()`**:
   ```python
   async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """Handle voice messages: download, transcribe via Gemini, create task."""
       api_key = os.getenv("GEMINI_API_KEY")
       if not api_key:
           await update.message.reply_text(
               "⚠️ שירות ה-AI לא מוגדר. פנה למנהל המערכת."
           )
           return ConversationHandler.END

       processing_msg = await update.message.reply_text("🎙️ מעבד הודעה קולית...")

       voice = update.message.voice
       tmp_path = None
       try:
           file = await voice.get_file()
           tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
           tmp_path = tmp.name
           tmp.close()
           await file.download_to_drive(tmp_path)
           logger.info(f"Voice file downloaded: {tmp_path} ({voice.duration}s)")

           from src.services.ai import parse_task_from_voice
           result = await asyncio.to_thread(parse_task_from_voice, tmp_path, api_key)
       except Exception as e:
           logger.error(f"Voice processing error: {e}", exc_info=True)
           await processing_msg.edit_text("❌ שגיאה בעיבוד ההודעה הקולית.")
           return ConversationHandler.END
       finally:
           if tmp_path:
               try:
                   os.unlink(tmp_path)
               except OSError:
                   pass

       if not result:
           await processing_msg.edit_text(
               "❌ לא הצלחתי לפרש את ההודעה הקולית. נסה שוב."
           )
           return ConversationHandler.END

       context.user_data["ai_task"] = result
       await _show_ai_confirmation(processing_msg, result)
       return AI_CONFIRM
   ```

6. **Update `ai_confirm_callback()`** — In the task creation section, change:
   - `sub_category="כללי"` → `sub_category=task_data.get("sub_category", "כללי")`

### C. `src/bot/bot_app.py` — Register voice entry point

1. **Update the ai_conv import** to also import `voice_handler`:
   ```python
   from src.bot.ai_handlers import (
       ai_command, ai_text_handler, ai_confirm_callback, ai_cancel,
       voice_handler,
       AI_WAITING_TEXT, AI_CONFIRM, AI_CONFIRM_SAVE, AI_CONFIRM_CANCEL
   )
   ```

2. **Add voice as entry point** to `ai_conv`:
   ```python
   ai_conv = ConversationHandler(
       entry_points=[
           CommandHandler('ai', ai_command),
           MessageHandler(filters.VOICE, voice_handler),
       ],
       states={
           AI_WAITING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_text_handler)],
           AI_CONFIRM: [CallbackQueryHandler(ai_confirm_callback, pattern=f"^({AI_CONFIRM_SAVE}|{AI_CONFIRM_CANCEL})$")],
       },
       fallbacks=[CommandHandler('cancel', ai_cancel)]
   )
   ```

**Code standards:**
- Use get_now() and to_naive_israel() for all datetime operations
- Session management: SessionLocal() with try/except/finally, rollback on error, close in finally
- Gemini system prompt via system_instruction parameter (NOT in content list)
- Run blocking Gemini calls via asyncio.to_thread()
- Clean up temp files in finally blocks
- All UI strings in Hebrew

After completing, verify:
```
python -c "from src.bot.ai_handlers import voice_handler, ai_command; from src.services.ai import parse_task_from_voice; print('Phase 5 OK')"
```
```

---

## PROMPT 6: Phase 6 — Category Management + CLAUDE.md Update

```
We are refactoring the TLI Telegram bot. This is Phase 6 (final): Category Management & Documentation.
Phases 1-5 are complete.

The project is at the current working directory. Read the CLAUDE.md for full context.

**What to do:**

### A. `src/bot/category_handlers.py` — Add projects section

Read the current file first.

1. **Add import**: `CATEGORY_PROJECTS` from `src.bot.constants`

2. **Add import**: `ensure_project_categories` from `src.database.core`

3. **Update `categories_command()`**:
   - Call `ensure_project_categories(session, chat_id)` right after the existing `ensure_user_categories(session, chat_id)` call
   - Query project categories: `project_cats = [c for c in categories if c.parent == CATEGORY_PROJECTS]`
   - After the Work section keyboard rows, add a spacer and Projects section:
     ```python
     # Spacer
     keyboard.append([InlineKeyboardButton("➖➖➖➖", callback_data="ignore")])

     # Projects Section
     keyboard.append([InlineKeyboardButton("📁 פרויקטים", callback_data="ignore")])
     for c in project_cats:
         keyboard.append([
             InlineKeyboardButton(c.name, callback_data="ignore"),
             InlineKeyboardButton("❌ מחק", callback_data=f"{DEL_CAT_PREFIX}{c.id}")
         ])
     keyboard.append([InlineKeyboardButton("➕ הוסף לפרויקטים", callback_data=f"{ADD_CAT_PREFIX}{CATEGORY_PROJECTS}")])
     ```

### B. Update `CLAUDE.md` — Reflect the refactor

Read the current CLAUDE.md, then update these sections:

1. **Tech Stack table**: Remove weather/calendar references. Keep APScheduler for reminders only.

2. **Core Features**:
   - Update "Daily Briefing" and "Evening Brief" to say "Archived — see archive/ directory"
   - Add "Projects" category description
   - Add "Voice Entry" feature description
   - Update task creation flow description (simplified for home/work)

3. **Project Structure**: Add `archive/` directory. Remove `src/services/weather.py` and `src/services/calendar.py`.

4. **Environment Variables table**:
   - Remove `OPENWEATHER_API_KEY`
   - Remove `GOOGLE_SERVICE_ACCOUNT_KEY`
   - Remove `CALENDAR_MAP`

5. **Startup Sequence**: Remove steps for briefing jobs, weather/calendar logging. Keep Gemini key check.

6. **Categories section**: Add `projects` as third parent category with its subcategories.

7. **Bot Patterns**: Add voice handler description. Update task creation trigger to include `פרויקטים`.

**Do NOT rewrite the entire CLAUDE.md** — only update the specific sections mentioned above. Preserve everything else (Fixed Issues Log, Known Quirks, etc.).

After completing, verify the full startup:
```
python -c "from src.bot.bot_app import create_app; from src.bot.category_handlers import categories_command; print('Phase 6 OK')"
```
```

---

## Execution Order

| Order | Prompt | Touches |
|-------|--------|---------|
| 1 | Phase 1 — Archive | scheduler/jobs, scheduler/service, main.py, services/, requirements.txt |
| 2 | Phase 2 — Database | constants.py, core.py, models.py |
| 3 | Phase 3 — Flow | handlers.py, bot_app.py |
| 4 | Phase 4 — Dashboard | dashboard_handlers.py |
| 5 | Phase 5 — AI/Voice | ai.py, ai_handlers.py, bot_app.py |
| 6 | Phase 6 — Categories/Docs | category_handlers.py, CLAUDE.md |

Each prompt is self-contained. Run them sequentially in separate Claude Code sessions.
