import logging
import os
from dotenv import load_dotenv

load_dotenv()

from src.database.core import init_db
from migrate_db import migrate
from src.scheduler.service import start_scheduler, add_daily_briefing_job, recover_missed_reminders
from src.bot.bot_app import create_app

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # 1. Verify Environment
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("FATAL: BOT_TOKEN is missing or empty")
        return
    masked = token[:5] + "..." + token[-5:]
    logger.info(f"BOT_TOKEN: {masked}")

    db_url = os.getenv("DATABASE_URL", "sqlite:///./tasks.db")
    if db_url.startswith("sqlite"):
        logger.info("DATABASE_URL: SQLite (local)")
    elif "@" in db_url:
        logger.info(f"DATABASE_URL: PostgreSQL @ {db_url.split('@')[-1]}")
    else:
        logger.info("DATABASE_URL: (set)")

    # 2. Initialize DB
    logger.info("Initializing Database...")
    init_db()

    # 2b. DB Connectivity Test
    from src.database.core import SessionLocal
    from sqlalchemy import text
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        logger.info("Database connectivity: OK")
    except Exception as e:
        logger.error(f"FATAL: Database connectivity test failed — {e}")
        return
    finally:
        session.close()

    # 2c. Run migrations (adds missing columns to existing tables)
    logger.info("Running migrations...")
    migrate()

    # 2d. Verify critical columns exist
    session = SessionLocal()
    try:
        session.execute(text("SELECT completed_at FROM tasks LIMIT 0"))
        logger.info("Schema verification: completed_at column OK")
    except Exception as e:
        logger.error(f"FATAL: completed_at column missing after migration — {e}")
        session.rollback()
        return
    finally:
        session.close()

    # 3. Start Scheduler
    logger.info("Starting Scheduler...")
    start_scheduler()
    add_daily_briefing_job()

    # 3b. Recover missed reminders (non-blocking — schedules via APScheduler)
    logger.info("Checking for missed reminders...")
    recover_missed_reminders()

    # 4. Start Bot
    logger.info("All startup steps completed. Launching polling...")
    try:
        app = create_app()
        logger.info(f"run_polling() called — bot should be live (token: {masked})")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"FATAL: Bot polling failed: {e}", exc_info=True)

if __name__ == '__main__':
    main()
