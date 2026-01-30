# CLAUDE.md — The Life Itself (TLI)

Primary context file for AI assistants working on this project.

---

## Project Overview

**The Life Itself (TLI)** is a Hebrew-language Telegram bot for personal task management. It lets users organize tasks by category (Home / Work), set priorities (Urgent / Normal / Low), schedule reminders, and receive a daily summary — all through an inline-keyboard-driven Telegram interface.

The bot is designed for a single user or small user base. All UI text is in Hebrew.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3 |
| Telegram API | `python-telegram-bot` (with `job-queue` and `callback-data` extras) |
| ORM | SQLAlchemy (declarative base) |
| Database | PostgreSQL (production) / SQLite (local dev) |
| Scheduler | APScheduler `BackgroundScheduler` with SQLAlchemy job store |
| Config | `python-dotenv` (.env file) |
| Deployment | Railway (Procfile-based) |

There is **no web framework** (no Flask / FastAPI). The bot uses long-polling via `python-telegram-bot`, not webhooks.

---

## Core Features

- **Task CRUD** — Create, view, edit, and mark tasks as done. Tasks have a description, priority, parent category (home/work), optional subcategory, and optional reminder.
- **Priority System** — Urgent (red), Normal (yellow), Low (green). Tasks are sorted by priority throughout the UI.
- **Categories** — Two parent categories: `home` and `work`. Each has user-manageable subcategories (e.g., Shopping, Maintenance, Emails, Meetings). Subcategories use soft delete (`is_active` flag).
- **Reminders** — Preset options: 1 hour, Tonight 20:00, Tomorrow 09:00, Tomorrow 09:30, 3 days, 1 week, None. Reminders can be snoozed by 1 hour. Scheduled via APScheduler with persistent job store.
- **Dashboard** (`/start`, `/dashboard`) — Time-of-day greeting, task counts per category (with urgent count), top 3 urgent tasks, today's upcoming reminders, quick filter buttons.
- **Quick Add** — Fast task creation that skips priority/subcategory selection (defaults to Home, Normal priority).
- **Daily Summary** — Automated job at 09:00 Israel time sends all pending tasks grouped by priority to each user.
- **Category Management** (`/categories`) — Add or soft-delete subcategories for Home and Work.

---

## Project Structure

```
The Life Itself/
├── main.py                    # Entry point: init DB → migrate → start scheduler → run bot
├── migrate_db.py              # Schema migration (adds missing columns)
├── verify_time.py             # Timezone verification script
├── check_subs.py              # Diagnostic: list all subcategories in DB
├── requirements.txt           # Python dependencies (no version pins)
├── Procfile                   # Railway/Heroku: worker: python main.py
├── .env.example               # Template: BOT_TOKEN=your_telegram_bot_token
├── .gitignore                 # Excludes: __pycache__, *.db, .env, .venv
│
├── src/
│   ├── bot/
│   │   ├── bot_app.py              # Telegram Application factory & handler registration
│   │   ├── handlers.py             # Core conversation handlers (create/edit/done/remind)
│   │   ├── dashboard_handlers.py   # Dashboard display & quick-add flow
│   │   ├── category_handlers.py    # Subcategory add/delete handlers
│   │   ├── keyboards.py            # InlineKeyboard builders (priority, reminder, subcategory)
│   │   ├── constants.py            # States, callback prefixes, priority/reminder/category enums
│   │   └── utils.py                # Timezone utilities: get_now(), to_naive_israel()
│   │
│   ├── database/
│   │   ├── core.py                 # Engine, SessionLocal, init_db() with default subcategory seeding
│   │   └── models.py               # ORM models: Task, SubCategory
│   │
│   └── scheduler/
│       ├── service.py              # APScheduler init, add_reminder_job(), add_daily_summary_job()
│       └── jobs.py                 # Job functions: send_reminder_job(), daily_summary_job()
```

---

## Infrastructure & Deployment

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram Bot API token |
| `DATABASE_URL` | No | PostgreSQL connection string. Defaults to `sqlite:///./tasks.db` for local dev. |

The database module auto-converts `postgres://` to `postgresql://` for Heroku/Railway compatibility.

### Deployment (Railway)

1. Push code to the git repository.
2. Railway detects the `Procfile` (`worker: python main.py`).
3. Dependencies installed from `requirements.txt`.
4. Environment variables (`BOT_TOKEN`, `DATABASE_URL`) set in Railway dashboard.
5. The bot starts: DB init → migration → scheduler → polling.

Manual deploy via CLI: `railway up`.

There is **no Docker setup** and **no CI/CD pipeline** — deployment is via Railway CLI or git-push integration.

### Startup Sequence (`main.py`)

1. Load `.env` via `python-dotenv`
2. `init_db()` — Creates tables via SQLAlchemy `create_all()`, seeds default subcategories
3. `migrate()` — Adds any missing columns (e.g., `recurrence`)
4. `start_scheduler()` — Starts APScheduler background thread
5. `add_daily_summary_job()` — Registers 09:00 daily cron job
6. `create_app()` + `app.run_polling()` — Starts Telegram long-polling

---

## Fixed Issues Log

### 1. Production Crash — Missing `recurrence` Column
- **Symptom**: All database queries failed after adding `recurrence` field to the Task model.
- **Root Cause**: `SQLAlchemy.create_all()` does not add new columns to existing tables. The production DB had the `tasks` table but lacked the `recurrence` column.
- **Fix**: Created `migrate_db.py` which runs `ALTER TABLE tasks ADD COLUMN recurrence VARCHAR`. Called `migrate()` on startup in `main.py` before the bot starts.
- **Commit**: `c40e161`

### 2. Task ID Race Condition — Reminders Not Sent
- **Symptom**: Reminder jobs were never triggered.
- **Root Cause**: `add_reminder_job(new_task.id, ...)` was called before `session.commit()`, so the task had no valid ID yet.
- **Fix**: Reordered operations to: create task → `session.commit()` → `session.refresh(new_task)` → register scheduler job.
- **Commit**: `e60604c`

### 3. Timezone Misalignment
- **Symptom**: Reminders fired at wrong times; dashboard showed incorrect "today's reminders".
- **Root Cause**: Mixed use of naive `datetime.now()` and timezone-aware datetimes. The scheduler expected Israel time but received UTC-based naive datetimes.
- **Fix**: Created centralized timezone utilities in `src/bot/utils.py`:
  - `get_now()` — returns current time as timezone-aware (`Asia/Jerusalem`)
  - `to_naive_israel()` — converts aware datetime to naive for DB storage
  - Configured APScheduler with explicit `timezone="Asia/Jerusalem"`
- **Commit**: `e60604c`

---

## Known Quirks & Guidelines

### Timezone Rules
- **Always** use `get_now()` from `src/bot/utils.py` instead of `datetime.now()`.
- **Always** use `to_naive_israel()` before storing datetimes in the database.
- The database stores **naive** datetimes (no tzinfo), assumed to be Israel time.
- The scheduler operates with **aware** datetimes in `Asia/Jerusalem`.
- The canonical timezone is `Asia/Jerusalem`.

### Database Patterns
- `SQLAlchemy.create_all()` only creates new tables — it will **not** add columns to existing tables. Any schema change to an existing table must go through `migrate_db.py`.
- SubCategories use **soft delete**: set `is_active = 0` instead of deleting rows.
- Default subcategories are seeded on first `init_db()` call (only if the table is empty).
- The `DATABASE_URL` env var is optional; without it, SQLite (`./tasks.db`) is used.

### Bot Patterns
- Task creation is triggered by sending text starting with `"בית"` (home) or `"עבודה"` (work).
- All conversation flows use `python-telegram-bot` `ConversationHandler` with states defined in `constants.py`.
- Callback data uses string prefixes (e.g., `view_task_`, `done_task_`, `snooze_1h_`) followed by the task ID.
- The bot uses polling, not webhooks.

### Code Conventions
- Hebrew-language UI strings are inline in handler files (no i18n framework).
- No version pins in `requirements.txt` — be cautious with dependency updates.
- Recurrence feature (`daily`, `weekly`, `monthly`) is partially implemented (column exists, constants defined, but no scheduling logic yet).

---

## Development Commands

```bash
# Setup
cp .env.example .env          # Then edit .env and set BOT_TOKEN

# Run locally (uses SQLite by default)
python main.py

# Verify timezone configuration
python verify_time.py

# Inspect subcategories in the database
python check_subs.py

# Deploy to Railway
railway up

# View Railway logs
railway logs
```
