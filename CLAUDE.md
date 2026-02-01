# CLAUDE.md — The Life Itself (TLI)

Primary context file for AI assistants working on this project.

---

## Project Overview

**The Life Itself (TLI)** is a Hebrew-language Telegram bot for personal task management. It lets users organize tasks by category (Home / Work), set priorities (Urgent / Normal / Low), schedule reminders, and receive a daily morning briefing — all through an inline-keyboard-driven Telegram interface.

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

- **Task CRUD** — Create, view, edit, and mark tasks as done. Tasks have a description, priority, parent category (home/work), optional subcategory, optional reminder, and `completed_at` timestamp.
- **Priority System** — Urgent (red), Normal (yellow), Low (green). Tasks are sorted by priority throughout the UI.
- **Categories** — Two parent categories: `home` and `work`. Each has user-manageable subcategories (e.g., Shopping, Maintenance, Emails, Meetings). Subcategories use soft delete (`is_active` flag).
- **Reminders** — Preset options: 1 hour, Tonight 20:00, Tomorrow 09:00, Tomorrow 09:30, 3 days, 1 week, None. Reminders can be snoozed by 1 hour. Scheduled via APScheduler with persistent job store.
- **Dashboard** (`/start`, `/dashboard`) — Time-of-day greeting, task counts per category (with urgent count), top 3 urgent tasks, today's upcoming reminders, quick filter buttons.
- **Quick Add** — Fast task creation that skips priority/subcategory selection (defaults to Home, Normal priority).
- **Daily Briefing** — Automated job at 09:35 Israel time. Includes a performance-based opening summary (based on yesterday's completions vs remaining), yesterday's completion count, top 3 personal and shared tasks with age indicators (🐢 >3 days, 🏛️ >7 days), and a link to the full list. Skips users with zero pending tasks and zero yesterday completions.
- **Evening Brief** — Automated job at 20:30 Israel time. Includes tomorrow's weather forecast with clothing recommendation for adults and children (via OpenWeatherMap), tomorrow's Google Calendar events (via service account auth, per-user calendar mapping), today's task completion summary, and urgent task alerts. Each section degrades gracefully if its data source is unavailable.
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
│   │   ├── keyboards.py            # InlineKeyboard builders (priority, reminder, subcategory) — subcategory has retry logic
│   │   ├── constants.py            # States, callback prefixes, priority/reminder/category enums
│   │   └── utils.py                # Timezone utilities: get_now(), to_naive_israel()
│   │
│   ├── database/
│   │   ├── core.py                 # Engine (with pool resilience for Neon), SessionLocal, init_db() with default subcategory seeding
│   │   └── models.py               # ORM models: Task, SubCategory
│   │
│   ├── services/
│   │   ├── __init__.py             # Services package marker
│   │   ├── weather.py              # OpenWeatherMap forecast + clothing recommendation
│   │   └── calendar.py             # Google Calendar service account auth + event fetching
│   │
│   └── scheduler/
│       ├── service.py              # APScheduler init, stale job cleanup, add_reminder_job(), recover_missed_reminders()
│       └── jobs.py                 # Job functions: send_reminder_job(), daily_briefing_job(), evening_brief_job()
```

---

## Infrastructure & Deployment

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram Bot API token |
| `DATABASE_URL` | No | PostgreSQL connection string. Defaults to `sqlite:///./tasks.db` for local dev. |
| `OPENWEATHER_API_KEY` | No | OpenWeatherMap API key for evening weather forecast. If missing, weather section is silently skipped. |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | No | Base64-encoded Google service account JSON for Calendar API. If missing, calendar section is skipped. |
| `CALENDAR_MAP` | No | Per-user calendar mapping: `chat_id:calendar_id` pairs, comma-separated. |

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

1. **Verify environment** — Validate `BOT_TOKEN` (abort if missing) and log masked `DATABASE_URL`
2. `init_db()` — Creates tables via SQLAlchemy `create_all()`, seeds default subcategories
3. **DB connectivity test** — `SELECT 1` (abort with `FATAL` if unreachable)
4. `migrate()` — Adds any missing columns using `TIMESTAMP`-compatible SQL. Uses `IF NOT EXISTS` on PostgreSQL.
5. **Schema verification** — `SELECT completed_at FROM tasks LIMIT 0` (abort if column missing)
6. `start_scheduler()` — Cleans stale jobs from persistent store via SQL, then starts APScheduler background thread
7. `add_daily_briefing_job()` — Registers 09:35 daily cron job
8. `add_evening_brief_job()` — Registers 20:30 daily cron job (weather + calendar + task reflection)
9. **Log optional service status** — Checks OpenWeatherMap API key and Google Calendar credentials, logs setup instructions if missing
10. `recover_missed_reminders()` — Non-blocking: schedules missed reminders as immediate APScheduler jobs (never calls `asyncio.run()` on the main thread)
11. `create_app()` + `app.run_polling(drop_pending_updates=True)` — Starts Telegram long-polling

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

### 4. Neon Cold-Start Connection Failures — Category Loading Error
- **Symptom**: Users frequently saw "שגיאה בטעינת קטגוריות" during task creation.
- **Root Cause**: Neon (serverless PostgreSQL) scales to zero when idle. The SQLAlchemy engine had no resilience configuration — no `pool_pre_ping`, no `pool_recycle`, no connection timeout. The first query on a stale pooled connection after Neon wakeup would fail.
- **Fix** (three layers):
  1. `core.py` — Added `pool_pre_ping=True`, `pool_recycle=300`, `pool_size=5`, `pool_timeout=30`, `connect_timeout=10` for PostgreSQL engines. SQLite path unchanged.
  2. `keyboards.py` — Added 3-attempt retry with 0.5s/1.0s backoff in `get_subcategory_keyboard()`, with timing + detail logging per attempt.
  3. `handlers.py` — `cancel()` now clears `context.user_data` keys. Error handlers in `priority_callback` and `shared_choice_callback` clear `user_data` and show improved Hebrew error message.
- **Commit**: `1e2d2c3`

### 5. Scheduler Crash — Ghost `daily_summary` Job in Persistent Store
- **Symptom**: `LookupError` on `scheduler.start()` — APScheduler could not deserialize a stored job referencing the removed `daily_summary_job` function.
- **Root Cause**: The daily summary job was renamed to `daily_briefing_job`, but the old `daily_summary` entry remained in the `apscheduler_jobs` table (persistent SQLAlchemy job store). On startup, APScheduler tries to deserialize all stored jobs and crashes if the referenced function no longer exists.
- **Fix**: Added `_clean_stale_jobs()` in `service.py` — runs raw SQL `DELETE FROM apscheduler_jobs WHERE id = :id` for all IDs in `_STALE_JOB_IDS` list before `scheduler.start()`. Uses `SessionLocal` with explicit rollback (not `engine.connect`).
- **Commit**: `e6839ed`

### 6. SQLAlchemy f405 — Dirty Pool Connections
- **Symptom**: Intermittent `sqlalchemy.exc.PendingRollbackError` (f405) — queries fail with "Can't reconnect until invalid transaction is rolled back".
- **Root Cause**: `migrate_db.py` and `_clean_stale_jobs()` used bare `engine.connect()`. When a query failed, the connection was returned to the pool without an explicit rollback, leaving it in a dirty state. The next caller that drew that connection from the pool got the f405 error.
- **Fix**: Replaced all `engine.connect()` usage in startup code with `SessionLocal()` wrapped in `try/except/finally` with explicit `session.rollback()` on error and `session.close()` in `finally`. This ensures connections are always returned to the pool in a clean state.
- **Commit**: `b89ce14`

### 7. Bot Unresponsive — Blocking `asyncio.run()` on Main Thread
- **Symptom**: Railway build succeeded and logs showed "Starting Scheduler...", but the bot never responded to Telegram commands.
- **Root Cause**: `recover_missed_reminders()` called `send_reminder_job()` directly for each missed reminder. `send_reminder_job()` uses `asyncio.run()`, which is a **blocking** call. With multiple missed reminders, `main()` never reached `app.run_polling()`.
- **Fix**: Changed `recover_missed_reminders()` to extract task data into tuples, close the session, then schedule each missed reminder as an immediate APScheduler job via `scheduler.add_job(run_date=datetime.now(timezone.utc))` — fully non-blocking. Also added `drop_pending_updates=True` to `run_polling()` and comprehensive startup diagnostics (env validation, DB connectivity test, schema verification).
- **Commit**: `3aa4804`

### 8. UndefinedColumn `completed_at` — Wrong SQL Type in Migration
- **Symptom**: `UndefinedColumn: column "completed_at" does not exist` on PostgreSQL after migration reported success.
- **Root Cause**: The migration SQL used `DATETIME`, which is not a valid PostgreSQL type. PostgreSQL requires `TIMESTAMP`. The migration silently failed (exception caught, logged as "skipped"), so the column was never created. SQLAlchemy ORM maps `Column(DateTime)` to `TIMESTAMP` automatically, but raw `ALTER TABLE` SQL must use the correct type explicitly.
- **Fix**: Changed migration SQL from `DATETIME` to `TIMESTAMP`. Added `IF NOT EXISTS` for PostgreSQL migrations (avoids noisy errors on re-runs). Added post-migration schema verification step in `main.py` — `SELECT completed_at FROM tasks LIMIT 0` — that aborts startup with `FATAL` if the column is missing.
- **Commit**: `c83cd5e`

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
- **Migration SQL types**: Use `TIMESTAMP` (not `DATETIME`) for date/time columns — PostgreSQL does not recognize `DATETIME`. Use `VARCHAR`, `BIGINT`, `INTEGER` for other types (portable across SQLite and PostgreSQL).
- **Migration idempotency**: PostgreSQL migrations use `ADD COLUMN IF NOT EXISTS`. SQLite does not support this syntax, so failures are caught and logged as "skipped".
- **Session management**: Always use `SessionLocal()` with `try/except/finally` — call `session.rollback()` on error, `session.close()` in `finally`. **Never** use bare `engine.connect()` for queries — it can leak dirty connections back to the pool, causing f405 errors for subsequent callers.
- SubCategories use **soft delete**: set `is_active = 0` instead of deleting rows.
- Default subcategories are seeded on first `init_db()` call (only if the table is empty).
- The `DATABASE_URL` env var is optional; without it, SQLite (`./tasks.db`) is used.
- **Connection resilience** (PostgreSQL/Neon only): The engine uses `pool_pre_ping=True` (auto-reconnect stale connections), `pool_recycle=300` (recycle before Neon idle timeout), and `connect_timeout=10`. These settings are **not** applied to SQLite. `get_subcategory_keyboard()` additionally retries up to 3 times with backoff as defense-in-depth.

### Bot Patterns
- Task creation is triggered by sending text starting with `"בית"` (home) or `"עבודה"` (work).
- All conversation flows use `python-telegram-bot` `ConversationHandler` with states defined in `constants.py`.
- Callback data uses string prefixes (e.g., `view_task_`, `done_task_`, `snooze_1h_`) followed by the task ID.
- The bot uses polling, not webhooks.

### Personality — Professional, Helpful, and Concise
The bot's tone is professional, direct, and supportive. Focus is on family productivity and clear communication.
- **Task completion** (`handlers.py`): When a task is marked done, the bot shows a concise confirmation message that varies by how long the task was open (< 5h quick, 5–48h normal, 2–7d delayed, > 7d long-standing). Phrases are defined in `_DONE_PHRASES` dict.
- **Daily briefing** (`jobs.py`): The morning message opens with a neutral/encouraging summary based on yesterday's performance bracket (amazing/good/meh/zero/clean). Hooks are defined in `_BRIEFING_HOOKS` dict.
- **Evening brief** (`jobs.py`): The evening message includes a factual summary of today's completion count (productive/decent/minimal/zero), plus an urgent task alert if applicable. Hooks are defined in `_EVENING_HOOKS` dict.

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
