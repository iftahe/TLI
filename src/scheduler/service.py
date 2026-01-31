import logging
from sqlalchemy import text
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from src.database.core import engine

logger = logging.getLogger(__name__)

jobstores = {
    'default': SQLAlchemyJobStore(engine=engine)
}

scheduler = BackgroundScheduler(
    jobstores=jobstores,
    timezone="Asia/Jerusalem",
    job_defaults={'misfire_grace_time': None, 'coalesce': True}
)

# Job IDs that were renamed or removed in past updates.
# Must be cleaned from the persistent store BEFORE scheduler.start(),
# because APScheduler deserializes all stored jobs on start and crashes
# with LookupError if the referenced function no longer exists.
_STALE_JOB_IDS = ['daily_summary']

def _clean_stale_jobs():
    """Remove ghost jobs from the persistent store via raw SQL.

    Uses SessionLocal (not engine.connect) so that failed queries get an
    explicit rollback — preventing dirty connections from leaking back into
    the pool and causing f405 errors in later callers.
    """
    from src.database.core import SessionLocal
    session = SessionLocal()
    try:
        for job_id in _STALE_JOB_IDS:
            result = session.execute(
                text("DELETE FROM apscheduler_jobs WHERE id = :id"),
                {"id": job_id}
            )
            if result.rowcount:
                logger.info(f"Cleaned stale job '{job_id}' from persistent store")
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(f"Could not clean stale jobs (table may not exist yet): {e}")
    finally:
        session.close()

def start_scheduler():
    _clean_stale_jobs()
    scheduler.start()

def add_reminder_job(task_id: int, run_date, chat_id: int):
    scheduler.add_job(
        'src.scheduler.jobs:send_reminder_job',
        'date',
        run_date=run_date,
        args=[task_id, chat_id],
        id=f'reminder_{task_id}',
        replace_existing=True
    )

def add_daily_briefing_job():
    if not scheduler.get_job('daily_briefing'):
        scheduler.add_job(
            'src.scheduler.jobs:daily_briefing_job',
            'cron',
            hour=9,
            minute=35,
            id='daily_briefing',
            replace_existing=True
        )

def recover_missed_reminders():
    """Schedule immediate delivery for reminders missed while the bot was offline.

    Uses scheduler.add_job() (non-blocking) instead of calling send_reminder_job()
    directly. Direct calls would invoke asyncio.run() on the main thread, blocking
    startup — the bot would never reach run_polling().
    """
    from src.database.core import SessionLocal
    from src.database.models import Task
    from src.bot.utils import get_now, to_naive_israel
    from datetime import datetime, timezone

    now_naive = to_naive_israel(get_now())
    session = SessionLocal()
    try:
        tasks = session.query(Task).filter(
            Task.status == 'pending',
            Task.reminder_time != None,
            Task.reminder_time <= now_naive
        ).all()

        if not tasks:
            logger.info("No missed reminders to recover.")
            return

        missed = [(t.id, t.chat_id) for t in tasks]
    except Exception as e:
        logger.error(f"Error querying missed reminders: {e}", exc_info=True)
        return
    finally:
        session.close()

    logger.info(f"Scheduling {len(missed)} missed reminder(s) for background delivery...")
    for task_id, chat_id in missed:
        try:
            scheduler.add_job(
                'src.scheduler.jobs:send_reminder_job',
                'date',
                run_date=datetime.now(timezone.utc),
                args=[task_id, chat_id],
                id=f'recover_{task_id}',
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"  Failed to schedule recovery for task {task_id}: {e}")
