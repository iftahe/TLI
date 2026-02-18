from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.core import SessionLocal
from src.database.models import Task
from src.bot.constants import CATEGORY_HOME, CATEGORY_WORK, CATEGORY_PROJECTS, PRIORITY_URGENT
from datetime import datetime, timedelta
from src.bot.utils import get_now, get_accessible_filter

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        chat_id = update.effective_chat.id
        now = get_now()

        # 1. Load all pending tasks and separate projects from main
        active_tasks = session.query(Task).filter(
            get_accessible_filter(chat_id),
            Task.status == 'pending'
        ).all()

        main_tasks = [t for t in active_tasks if t.parent_category != CATEGORY_PROJECTS]
        project_tasks = [t for t in active_tasks if t.parent_category == CATEGORY_PROJECTS]

        # 2. Counts (from main_tasks only)
        home_count = sum(1 for t in main_tasks if t.parent_category == CATEGORY_HOME)
        work_count = sum(1 for t in main_tasks if t.parent_category == CATEGORY_WORK)
        projects_count = len(project_tasks)
        total = len(main_tasks)
        urgent_count = sum(1 for t in main_tasks if t.priority == PRIORITY_URGENT)

        # 3. "Today" count — main tasks with reminder_time set for today
        now_naive = now.replace(tzinfo=None)
        today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now_naive.replace(hour=23, minute=59, second=59)

        today_tasks = [t for t in main_tasks
                       if t.reminder_time and today_start <= t.reminder_time <= today_end]
        today_count = len(today_tasks)

        # 4. Upcoming reminders (from now to end of day, main_tasks only)
        reminders = [t for t in main_tasks
                     if t.reminder_time and now_naive <= t.reminder_time <= today_end]
        reminders.sort(key=lambda t: t.reminder_time)

        # 5. Urgent tasks (top 3, main_tasks only)
        urgent_tasks = [t for t in main_tasks if t.priority == PRIORITY_URGENT]
        urgent_tasks.sort(key=lambda t: t.created_at or now)
        top_urgent = urgent_tasks[:3]

        # Build Message
        greeting_time = "בוקר" if 5 <= now.hour < 12 else "צהריים" if 12 <= now.hour < 18 else "ערב"
        date_str = now.strftime("%d/%m")

        msg = f"👋 <b>{greeting_time} טוב!</b>\n"
        msg += f"📅 {date_str}\n\n"

        # KPI row
        msg += f"📌 היום: <b>{today_count}</b>"
        msg += f"  ·  🏠 בית: <b>{home_count}</b>"
        msg += f"  ·  💼 עבודה: <b>{work_count}</b>\n"
        msg += f"סה״כ: <b>{total}</b> משימות פתוחות\n"

        if urgent_count > 0:
            msg += f"🔴 דחוף: {urgent_count}\n"

        if top_urgent:
            msg += "\n🔥 <b>דחוף:</b>\n"
            for t in top_urgent:
                cat = "🏠" if t.parent_category == CATEGORY_HOME else "💼"
                msg += f"  {cat} {t.text}\n"

        if reminders:
            msg += "\n🔔 <b>תזכורות להיום:</b>\n"
            for t in reminders:
                t_str = t.reminder_time.strftime("%H:%M")
                msg += f"  {t_str} — {t.text}\n"

        # Build Keyboard
        keyboard = [
            [
                InlineKeyboardButton(f"📌 היום ({today_count})", callback_data="filter_today"),
                InlineKeyboardButton(f"🏠 בית ({home_count})", callback_data="filter_home"),
                InlineKeyboardButton(f"💼 עבודה ({work_count})", callback_data="filter_work"),
            ],
            [
                InlineKeyboardButton(f"📁 פרויקטים ({projects_count})", callback_data="filter_projects"),
            ],
        ]

        markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text(msg, reply_markup=markup, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=markup, parse_mode='HTML')

    finally:
        session.close()

async def quick_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚡ **הוספה מהירה**\nכתוב את המשימה שלך (היא תתווסף ל'כללי' בעדיפות רגילה):",
        parse_mode='Markdown'
    )
    return "QUICK_ADD_WAITING" # Needs state definition
