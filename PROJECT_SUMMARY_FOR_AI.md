# The Life Itself (TLI) — Full Project Summary

## Overview

Hebrew-language Telegram bot for personal/shared task management. Supports categories (Home/Work), priorities (Urgent/Normal/Low), reminders, daily morning briefing (09:35), evening brief (20:30 — weather + calendar + task reflection), and subcategory management. Designed for single user or small household. Deployed on Railway via long-polling (no webhooks).

---

## Tech Stack

- **Language**: Python 3
- **Telegram**: `python-telegram-bot` (with `job-queue` and `callback-data` extras)
- **ORM**: SQLAlchemy (declarative base)
- **Database**: PostgreSQL (production on Neon) / SQLite (local dev)
- **Scheduler**: APScheduler `BackgroundScheduler` with SQLAlchemy persistent job store
- **Config**: `python-dotenv`
- **Deployment**: Railway (Procfile: `worker: python main.py`)
- **No web framework** — pure Telegram bot with polling

---

## Project Structure

```
The Life Itself/
├── main.py                         # Entry point: env check → init DB → migrate → scheduler → polling
├── migrate_db.py                   # Raw SQL schema migrations (ALTER TABLE)
├── verify_time.py                  # Timezone verification diagnostic
├── check_subs.py                   # Subcategory listing diagnostic
├── test_calendar.py                # Google Calendar integration diagnostic
├── requirements.txt                # Dependencies (no version pins)
├── Procfile                        # worker: python main.py
├── .env.example                    # Template for environment variables
│
├── src/
│   ├── bot/
│   │   ├── bot_app.py              # Telegram Application factory & all handler registration
│   │   ├── handlers.py             # Core conversation handlers (create/edit/done/remind/list/view)
│   │   ├── dashboard_handlers.py   # Dashboard display & quick-add flow
│   │   ├── category_handlers.py    # Subcategory add/delete handlers
│   │   ├── keyboards.py            # InlineKeyboard builders (priority, reminder, subcategory)
│   │   ├── constants.py            # States, callback prefixes, priority/reminder/category enums
│   │   └── utils.py                # Timezone (get_now, to_naive_israel), auth (ALLOWED_USERS), shared task filters
│   │
│   ├── database/
│   │   ├── core.py                 # Engine config (Neon resilience), SessionLocal, init_db(), default category seeding
│   │   └── models.py               # ORM models: Task, SubCategory
│   │
│   ├── services/
│   │   ├── __init__.py             # Package marker
│   │   ├── weather.py              # OpenWeatherMap: tomorrow forecast + clothing recommendation
│   │   └── calendar.py             # Google Calendar: service account auth + tomorrow's events
│   │
│   └── scheduler/
│       ├── service.py              # APScheduler init, stale job cleanup, add/recover reminder jobs
│       └── jobs.py                 # Job functions: send_reminder, daily_briefing, evening_brief
```

---

## Database Schema

### Task (`tasks` table)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto-increment |
| chat_id | BigInteger (indexed) | Telegram user ID |
| text | String | Task description |
| priority | String | `'urgent'` / `'normal'` / `'low'` |
| parent_category | String | `'home'` / `'work'` |
| sub_category | String (nullable) | Subcategory name |
| reminder_time | DateTime (nullable) | Naive datetime in Israel TZ |
| status | String | `'pending'` / `'done'` |
| recurrence | String (nullable) | `'daily'`/`'weekly'`/`'monthly'` (partially implemented) |
| is_shared | Integer | 0 or 1 (shared Home tasks visible to all users) |
| created_at | DateTime | Auto-set on creation |
| completed_at | DateTime (nullable) | Set when marked done |

### SubCategory (`sub_categories` table)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto-increment |
| chat_id | BigInteger (nullable, indexed) | 0 = shared, else user's Telegram ID |
| name | String | Display name with emoji (e.g., "קניות 🛒") |
| parent | String | `'home'` / `'work'` |
| is_active | Integer | 1 = active, 0 = soft-deleted |

**Default Home subcategories**: קניות 🛒, תחזוקה 🔧, ניקיון 🧹, אחר 📂
**Default Work subcategories**: מיילים 📧, פגישות 📅, פרויקטים 📊, אחר 📂

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram Bot API token |
| `DATABASE_URL` | No | PostgreSQL connection string. Default: `sqlite:///./tasks.db` |
| `OPENWEATHER_API_KEY` | No | For evening weather forecast. Skipped if missing. |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | No | Base64-encoded Google service account JSON. Skipped if missing. |
| `CALENDAR_MAP` | No | `chat_id1:calendar_id1,chat_id2:calendar_id2` |
| `ALLOWED_USERS` | No | Comma-separated user IDs. No restriction if empty. |

---

## Startup Sequence (main.py)

1. Validate `BOT_TOKEN` (abort if missing)
2. `init_db()` — create tables, seed default subcategories
3. DB connectivity test (`SELECT 1`)
4. `migrate()` — add missing columns via raw SQL
5. Schema verification (`SELECT completed_at FROM tasks LIMIT 0`)
6. `start_scheduler()` — clean stale jobs, start APScheduler
7. Register daily briefing job (09:35) and evening brief job (20:30)
8. Log optional service status (weather, calendar)
9. `recover_missed_reminders()` — schedule missed as immediate jobs (non-blocking)
10. `create_app()` + `app.run_polling(drop_pending_updates=True)`

---

## Conversation Flows

### Task Creation
1. User sends message starting with `"בית"` (home) or `"עבודה"` (work), optionally followed by description
2. If no inline description → ask for description (DESCRIPTION state)
3. Select priority: Urgent 🔴 / Normal 🟡 / Low 🟢 (PRIORITY state)
4. If Home → ask shared/personal: 👤 / 👥 (SHARED_CHOICE state)
5. Select subcategory from user's active list (SUB_CATEGORY state)
6. Select reminder: 1h / Tonight 20:00 / Tomorrow 09:00 / Tomorrow 09:30 / 3 days / 1 week / Custom / None (REMINDER state)
7. Create task in DB → schedule reminder job → confirmation message → END

### Quick Add
- Button press → type text → create with defaults (Home, Normal, "כללי", no reminder)

### Dashboard (`/start`, `/dashboard`)
- Time-of-day greeting (morning/afternoon/evening)
- Task counts: Home (personal + shared), Work, Urgent breakdown
- Top 3 urgent tasks with age indicators (🐢 >3d, 🏛️ >7d)
- Today's upcoming reminders
- Filter buttons: 🏠 Home / 💼 Work

### Task List & Management (`/list`)
- Grouped by category → subcategory, sorted by priority
- View task → details with buttons: Done ✅, Edit Description ✏️, Edit Reminder ⏰, Back
- Mark done → completion feedback phrase (varies by task age) → auto-return to dashboard
- Snooze reminder → +1 hour

### Category Management (`/categories`)
- List active subcategories per parent (Home/Work)
- Add new subcategory / soft-delete existing ones

---

## Scheduled Jobs

### Daily Briefing (09:35 Israel time)
- Performance-based opening hook (amazing/good/meh/zero/clean bracket)
- Yesterday's completion count
- Top 3 personal + shared tasks with age indicators
- Link to `/list`
- Skips users with 0 pending + 0 completed

### Evening Brief (20:30 Israel time)
- **Weather**: Tomorrow's forecast (OpenWeatherMap) + clothing recommendation for adults and children
- **Calendar**: Tomorrow's Google Calendar events (per-user mapping via service account)
- **Task Reflection**: Today's completion summary + urgent task alert
- Each section degrades gracefully if data source unavailable

### Reminders
- Scheduled via APScheduler with persistent SQLAlchemy job store
- On fire: sends Telegram message with Snooze (1h) and Edit buttons
- Missed reminders recovered on startup as immediate jobs

---

## Bot Personality

Professional, direct, and supportive. Hebrew UI. Key personality touches:

- **Task completion** (`_DONE_PHRASES`): Feedback varies by task age — < 5h (quick), 5–48h (normal), 2–7d (delayed), >7d (long-standing)
- **Morning briefing** (`_BRIEFING_HOOKS`): Performance-based opener
- **Evening brief** (`_EVENING_HOOKS`): Completion reflection (productive/decent/minimal/zero)

---

## Key Patterns

### Timezone
- Always `get_now()` instead of `datetime.now()` — returns aware Israel TZ
- Always `to_naive_israel()` before DB storage
- DB stores naive datetimes (assumed Israel time)
- Scheduler uses aware `Asia/Jerusalem`

### Database
- `create_all()` doesn't add columns to existing tables → use `migrate_db.py`
- Migration SQL: use `TIMESTAMP` not `DATETIME` (PostgreSQL compatibility)
- PostgreSQL migrations use `ADD COLUMN IF NOT EXISTS`
- Session: always `try/except/finally` with `rollback()` on error, `close()` in finally
- Never use bare `engine.connect()` — causes dirty pool connections (f405)

### Connection Resilience (Neon/PostgreSQL)
- Engine: `pool_pre_ping=True`, `pool_recycle=300`, `pool_size=5`, `connect_timeout=10`
- Subcategory keyboard: 3-attempt retry with 0.5s/1s/2s backoff

### Callback Data Format
- Prefixed strings: `view_task_<id>`, `done_task_<id>`, `snooze_1h_<id>`, `edit_rem_<id>`, `upd_rem_<id>_<choice>`

---

## Known Partial Implementations
- **Recurrence**: Column exists in Task model, constants defined (`daily`/`weekly`/`monthly`), but no scheduling logic yet
