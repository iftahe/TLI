from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from src.database.core import engine

jobstores = {
    'default': SQLAlchemyJobStore(engine=engine)
}

scheduler = BackgroundScheduler(jobstores=jobstores, timezone="Asia/Jerusalem")

def start_scheduler():
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

def add_daily_summary_job():
    if not scheduler.get_job('daily_summary'):
        scheduler.add_job(
            'src.scheduler.jobs:daily_summary_job',
            'cron',
            hour=9,
            minute=0,
            id='daily_summary',
            replace_existing=True
        )
