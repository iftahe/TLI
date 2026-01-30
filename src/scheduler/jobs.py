import asyncio
import logging
import os
from telegram import Bot
from src.database.core import SessionLocal
from src.database.models import Task

logger = logging.getLogger(__name__)

async def send_message_async(chat_id, text, reply_markup=None):
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found inside job")
        return
    async with Bot(token=token) as bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', reply_markup=reply_markup)

def send_reminder_job(task_id, chat_id):
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id).first()
        if task and task.status != 'done':
            logger.info(f"Sending reminder for task {task_id} to chat {chat_id}")
            text = f"⏰ <b>תזכורת למשימה:</b>\n{task.text}"

            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            from src.bot.constants import SNOOZE_1H_PREFIX, EDIT_TASK, VIEW_TASK

            keyboard = [
                [InlineKeyboardButton("💤 נודניק (1 שעה)", callback_data=f"{SNOOZE_1H_PREFIX}{task.id}")],
                [InlineKeyboardButton("✏️ ערוך/צפה", callback_data=f"{VIEW_TASK}{task.id}")]
            ]
            markup = InlineKeyboardMarkup(keyboard)

            asyncio.run(send_message_async(chat_id, text, reply_markup=markup))
            logger.info(f"Reminder sent successfully for task {task_id}")
        else:
            logger.info(f"Skipping reminder for task {task_id}: task not found or already done")
    except Exception as e:
        logger.error(f"Error in send_reminder_job for task {task_id}: {e}", exc_info=True)
    finally:
        session.close()

def daily_summary_job():
    from src.bot.utils import ALLOWED_USERS

    session = SessionLocal()
    try:
        tasks = session.query(Task).filter(Task.status == 'pending').all()

        # Separate personal and shared tasks
        shared_tasks = [t for t in tasks if t.is_shared and t.parent_category == 'home']
        personal_tasks = [t for t in tasks if not t.is_shared]

        # Build per-user task lists (personal tasks grouped by owner)
        user_tasks = {}
        for task in personal_tasks:
            if task.chat_id not in user_tasks:
                user_tasks[task.chat_id] = []
            user_tasks[task.chat_id].append(task)

        # Add shared tasks to ALL known users (owners + allowed users)
        all_user_ids = set(user_tasks.keys())
        if ALLOWED_USERS:
            all_user_ids.update(ALLOWED_USERS)

        for uid in all_user_ids:
            if uid not in user_tasks:
                user_tasks[uid] = []
            for st in shared_tasks:
                if st not in user_tasks[uid]:
                    user_tasks[uid].append(st)

        for chat_id, tasks_list in user_tasks.items():
            if not tasks_list:
                continue

            priority_order = {'urgent': 0, 'normal': 1, 'low': 2}
            tasks_list.sort(key=lambda t: priority_order.get(t.priority, 99))

            msg = "📋 <b>סיכום יומי:</b>\n\n"
            for t in tasks_list:
                icon = "🔴" if t.priority == 'urgent' else "🟡" if t.priority == 'normal' else "🟢"
                shared_mark = " 👥" if t.is_shared else ""
                msg += f"{icon} {t.text}{shared_mark}\n"

            try:
                asyncio.run(send_message_async(chat_id, msg))
                logger.info(f"Daily summary sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send daily summary to chat {chat_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error in daily_summary_job: {e}", exc_info=True)
    finally:
        session.close()
