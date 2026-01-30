from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.core import SessionLocal
from src.database.models import Task
from src.bot.constants import CATEGORY_HOME, CATEGORY_WORK, PRIORITY_URGENT
from datetime import datetime, timedelta
from src.bot.utils import get_now, get_accessible_filter

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        chat_id = update.effective_chat.id
        now = get_now()

        # 1. Stats
        active_tasks = session.query(Task).filter(
            get_accessible_filter(chat_id),
            Task.status == 'pending'
        ).all()

        home_personal = sum(1 for t in active_tasks if t.parent_category == CATEGORY_HOME and not t.is_shared)
        home_shared = sum(1 for t in active_tasks if t.parent_category == CATEGORY_HOME and t.is_shared)
        work_count = sum(1 for t in active_tasks if t.parent_category == CATEGORY_WORK)
        total = len(active_tasks)

        urgent_personal = sum(1 for t in active_tasks if t.priority == PRIORITY_URGENT and not t.is_shared)
        urgent_shared = sum(1 for t in active_tasks if t.priority == PRIORITY_URGENT and t.is_shared)

        # 2. Upcoming Reminders (Today)
        end_of_day = now.replace(hour=23, minute=59, second=59)
        now_naive = now.replace(tzinfo=None)
        end_of_day_naive = end_of_day.replace(tzinfo=None)

        reminders = session.query(Task).filter(
            get_accessible_filter(chat_id),
            Task.status == 'pending',
            Task.reminder_time >= now_naive,
            Task.reminder_time <= end_of_day_naive
        ).order_by(Task.reminder_time).all()

        # 3. Urgent Tasks (Top 3)
        urgent_tasks = [t for t in active_tasks if t.priority == 'urgent']
        urgent_tasks.sort(key=lambda t: t.created_at or now)
        top_urgent = urgent_tasks[:3]

        # Build Message
        greeting_time = "בוקר" if 5 <= now.hour < 12 else "צהריים" if 12 <= now.hour < 18 else "ערב"
        date_str = now.strftime("%d/%m")

        msg = f"👋 <b>{greeting_time} טוב!</b>\n"
        msg += f"📅 {date_str}\n\n"

        # KPI row
        msg += f"🏠 בית: <b>{home_personal}</b>"
        msg += f"  ·  👥 משותף: <b>{home_shared}</b>"
        msg += f"  ·  💼 עבודה: <b>{work_count}</b>\n"
        msg += f"סה״כ: <b>{total}</b> משימות פתוחות\n"

        if urgent_personal or urgent_shared:
            parts = []
            if urgent_personal:
                parts.append(f"{urgent_personal} אישי")
            if urgent_shared:
                parts.append(f"{urgent_shared} משותף")
            msg += f"🔴 דחוף: {' · '.join(parts)}\n"

        if top_urgent:
            msg += "\n🔥 <b>דחוף:</b>\n"
            for t in top_urgent:
                shared = " 👥" if t.is_shared else ""
                cat = "🏠" if t.parent_category == CATEGORY_HOME else "💼"
                msg += f"  {cat} {t.text}{shared}\n"

        if reminders:
            msg += "\n🔔 <b>תזכורות:</b>\n"
            for t in reminders:
                t_str = t.reminder_time.strftime("%H:%M")
                shared = " 👥" if t.is_shared else ""
                msg += f"  {t_str} — {t.text}{shared}\n"

        # Build Keyboard
        keyboard = [
            [
                InlineKeyboardButton(f"🏠 בית ({home_personal + home_shared})", callback_data="filter_home"),
                InlineKeyboardButton(f"💼 עבודה ({work_count})", callback_data="filter_work")
            ]
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
