from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.core import SessionLocal
from src.database.models import Task
from src.bot.constants import CATEGORY_HOME, CATEGORY_WORK, PRIORITY_URGENT
from datetime import datetime, timedelta

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        chat_id = update.effective_chat.id
        now = datetime.now()
        
        # 1. Stats
        active_tasks = session.query(Task).filter(
            Task.chat_id == chat_id, 
            Task.status == 'pending'
        ).all()
        
        home_count = sum(1 for t in active_tasks if t.parent_category == CATEGORY_HOME)
        work_count = sum(1 for t in active_tasks if t.parent_category == CATEGORY_WORK)
        
        home_urgent = sum(1 for t in active_tasks if t.parent_category == CATEGORY_HOME and t.priority == PRIORITY_URGENT)
        work_urgent = sum(1 for t in active_tasks if t.parent_category == CATEGORY_WORK and t.priority == PRIORITY_URGENT)
        
        today_completed = session.query(Task).filter(
             Task.chat_id == chat_id,
             Task.status == 'done',
             # Assuming we don't have completed_at yet, we can't accurately enable this line.
             # Task.created_at >= now.replace(hour=0, minute=0, second=0) 
        ).count()

        # 2. Upcoming Reminders (Today)
        end_of_day = now.replace(hour=23, minute=59, second=59)
        reminders = session.query(Task).filter(
            Task.chat_id == chat_id,
            Task.status == 'pending',
            Task.reminder_time >= now,
            Task.reminder_time <= end_of_day
        ).order_by(Task.reminder_time).all()
        
        # 3. Urgent Tasks (Top 3)
        urgent_tasks = [t for t in active_tasks if t.priority == 'urgent']
        urgent_tasks.sort(key=lambda t: t.created_at or now) # oldest first
        top_urgent = urgent_tasks[:3]

        # Build Message
        greeting_time = "בוקר" if 5 <= now.hour < 12 else "צהריים" if 12 <= now.hour < 18 else "ערב"
        date_str = now.strftime("%d/%m")
        day_name = now.strftime("%A") # English day name, mapping to Hebrew would be nice but keeping simple
        
        msg = f"👋 **{greeting_time} טוב!**\n"
        msg += f"📅 {date_str}\n\n"
        
        msg += "📊 **תמונת מצב:**\n"
        msg += f"🏠 **בית:** {home_count} (🔴 {home_urgent})\n"
        msg += f"💼 **עבודה:** {work_count} (🔴 {work_urgent})\n"
        # msg += f"✅ **הושלמו היום:** {today_completed}\n" 
        
        if top_urgent:
             msg += "\n🔥 **דחוף ביותר:**\n"
             for t in top_urgent:
                 cat = "🏠" if t.parent_category == CATEGORY_HOME else "💼"
                 msg += f"• {cat} {t.text}\n"

        if reminders:
            msg += "\n🔔 **תזכורות להיום:**\n"
            for t in reminders:
                t_str = t.reminder_time.strftime("%H:%M")
                msg += f"• {t_str} - {t.text}\n"
        else:
            msg += "\n🎉 אין עוד תזכורות להיום!\n"

        # Build Keyboard
        keyboard = [
            [
                InlineKeyboardButton("🏠 בית", callback_data="filter_home"), # Fallback or specific filter
                InlineKeyboardButton("💼 עבודה", callback_data="filter_work")
            ]
        ]
        
        markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(msg, reply_markup=markup, parse_mode='Markdown')
        elif update.callback_query:
             # If we are navigating back to dashboard, edit message
            await update.callback_query.edit_message_text(msg, reply_markup=markup, parse_mode='Markdown')

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
