import asyncio
import os
from telegram import Bot
from src.database.core import SessionLocal
from src.database.models import Task

async def send_message_async(chat_id, text, reply_markup=None):
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("BOT_TOKEN not found inside job")
        return
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', reply_markup=reply_markup)

def send_reminder_job(task_id, chat_id):
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id).first()
        if task and task.status != 'done':
            text = f"⏰ <b>תזכורת למשימה:</b>\n{task.text}"
            
            # Inline Keyboard for Snooze/Edit
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            # Note: We need to import SNOOZE_1H_PREFIX and EDIT_TASK constant but circular import might be issue. 
            # We will use string literals or local import to avoid circular dependency if possible, or move constants to shared.
            # Assuming constants.py does not import jobs.py, so it should be fine.
            from src.bot.constants import SNOOZE_1H_PREFIX, EDIT_TASK, VIEW_TASK
            
            keyboard = [
                [InlineKeyboardButton("💤 נודניק (1 שעה)", callback_data=f"{SNOOZE_1H_PREFIX}{task.id}")],
                [InlineKeyboardButton("✏️ ערוך/צפה", callback_data=f"{VIEW_TASK}{task.id}")]
            ]
            markup = InlineKeyboardMarkup(keyboard)
            
            asyncio.run(send_message_async(chat_id, text, reply_markup=markup))
    except Exception as e:
        print(f"Error in send_reminder_job: {e}")
    finally:
        session.close()

def daily_summary_job():
    session = SessionLocal()
    try:
        tasks = session.query(Task).filter(Task.status == 'pending').all()
        user_tasks = {}
        for task in tasks:
            if task.chat_id not in user_tasks:
                user_tasks[task.chat_id] = []
            user_tasks[task.chat_id].append(task)
        
        for chat_id, tasks_list in user_tasks.items():
            if not tasks_list:
                continue
            
            # Sort simple: urgent, normal, low
            priority_order = {'urgent': 0, 'normal': 1, 'low': 2}
            tasks_list.sort(key=lambda t: priority_order.get(t.priority, 99))

            msg = "📋 <b>סיכום יומי:</b>\n\n"
            for t in tasks_list:
                icon = "🔴" if t.priority == 'urgent' else "🟡" if t.priority == 'normal' else "🟢"
                msg += f"{icon} {t.text}\n"
            
            asyncio.run(send_message_async(chat_id, msg))
    except Exception as e:
        print(f"Error in daily_summary_job: {e}")
    finally:
        session.close()
