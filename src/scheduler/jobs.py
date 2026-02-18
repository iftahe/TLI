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
                [InlineKeyboardButton("💤 דחייה (שעה)", callback_data=f"{SNOOZE_1H_PREFIX}{task.id}")],
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
