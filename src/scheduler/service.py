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
    """Send reminders for tasks whose reminder_time has passed but were never delivered.
    This handles cases where the bot was restarted and APScheduler dropped the jobs.

    The session is closed BEFORE calling send_reminder_job (which creates its
    own session). Task data is extracted into plain tuples first to avoid
    lazy-loading on detached ORM objects.
    """
    from src.database.core import SessionLocal
    from src.database.models import Task
    from src.bot.utils import get_now, to_naive_israel

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

        # Extract into plain tuples before closing session
        missed = [(t.id, t.chat_id) for t in tasks]
    except Exception as e:
        logger.error(f"Error querying missed reminders: {e}", exc_info=True)
        return
    finally:
        session.close()

    logger.info(f"Recovering {len(missed)} missed reminder(s)...")
    from src.scheduler.jobs import send_reminder_job
    for task_id, chat_id in missed:
        try:
            logger.info(f"  Sending missed reminder for task {task_id} (chat_id={chat_id})")
            send_reminder_job(task_id, chat_id)
        except Exception as e:
            logger.error(f"  Failed to recover reminder for task {task_id}: {e}")
