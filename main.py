import logging
import os
from dotenv import load_dotenv

load_dotenv()

from src.database.core import init_db
from migrate_db import migrate
from src.scheduler.service import start_scheduler, add_daily_summary_job
from src.bot.bot_app import create_app

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # 1. Verify Token
    token = os.getenv("BOT_TOKEN")
    if token:
        masked = token[:5] + "..." + token[-5:]
        logger.info(f"BOT_TOKEN found: {masked}")
    else:
        logger.error("BOT_TOKEN is missing or empty in .env")
        return

    # 2. Initialize DB
    logger.info("Initializing Database...")
    init_db()

    # 2b. Run migrations (adds missing columns to existing tables)
    logger.info("Running migrations...")
    migrate()

    # 3. Start Scheduler
    logger.info("Starting Scheduler...")
    start_scheduler()
    add_daily_summary_job()

    # 4. Start Bot
    logger.info("Starting Bot...")
    try:
        app = create_app()
        logger.info("Polling started...")
        app.run_polling()
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)

if __name__ == '__main__':
    main()
