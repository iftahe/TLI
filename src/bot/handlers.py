import re
import logging
from datetime import datetime, timedelta
from src.bot.utils import get_now, to_naive_israel, ISRAEL_TZ
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from src.bot.constants import *
from src.bot.keyboards import get_priority_keyboard, get_subcategory_keyboard, get_reminder_keyboard
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.database.core import SessionLocal
from src.database.models import Task, SubCategory
from src.scheduler.service import add_reminder_job

logger = logging.getLogger(__name__)

def parse_custom_time(text: str):
    """Parse HH:MM or DD/MM HH:MM into an aware Israel datetime.
    Returns (datetime, error_message). On success error_message is None."""
    text = text.strip()
    now = get_now()

    # Try DD/MM HH:MM
    m = re.match(r'^(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})$', text)
    if m:
        day, month, hour, minute = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        try:
            reminder = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            return None, "תאריך לא תקין. נסה שוב בפורמט DD/MM HH:MM"
        if reminder <= now:
            return None, "הזמן שהוזן כבר עבר. הזן זמן עתידי."
        return reminder, None

    # Try HH:MM
    m = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            return None, "שעה לא תקינה. נסה שוב בפורמט HH:MM"
        reminder = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if reminder <= now:
            reminder += timedelta(days=1)
        return reminder, None

    return None, "פורמט לא תקין. שלח HH:MM או DD/MM HH:MM"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("אנא התחל משימה עם 'בית' או 'עבודה'.")
    return ConversationHandler.END

async def task_entry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith('בית'):
        context.user_data['parent'] = CATEGORY_HOME
        rest = text[3:].strip()
    elif text.startswith('עבודה'):
        context.user_data['parent'] = CATEGORY_WORK
        rest = text[5:].strip()
    else:
        return ConversationHandler.END

    if not rest:
        await update.message.reply_text("מה המשימה?")
        return DESCRIPTION
    
    context.user_data['description'] = rest
    await update.message.reply_text(
        f"משימה: {rest}\nבחר עדיפות:",
        reply_markup=get_priority_keyboard()
    )
    return PRIORITY

async def description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    await update.message.reply_text(
        "בחר עדיפות:",
        reply_markup=get_priority_keyboard()
    )
    return PRIORITY

async def priority_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    priority = query.data
    context.user_data['priority'] = priority

    parent = context.user_data.get('parent')
    try:
        keyboard = get_subcategory_keyboard(parent, chat_id=update.effective_chat.id)
    except Exception as e:
        logger.error(f"Error building subcategory keyboard: {e}", exc_info=True)
        await query.edit_message_text("❌ שגיאה בטעינת קטגוריות. נסה שוב עם /cancel ואז התחל משימה חדשה.")
        return ConversationHandler.END

    await query.edit_message_text(
        text="עדיפות נבחרה. קטגוריה:",
        reply_markup=keyboard
    )
    return SUB_CATEGORY

async def subcategory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    sub_data = query.data
    if sub_data.startswith('sub_'):
        try:
            sub_id = int(sub_data.replace('sub_', ''))
            # Fetch name
            session = SessionLocal()
            cat = session.query(SubCategory).filter(SubCategory.id == sub_id).first()
            name = cat.name if cat else "כללי"
            session.close()
        except ValueError:
             name = "כללי"
    else:
        name = "כללי"

    context.user_data['subcategory'] = name
    
    await query.edit_message_text(
        text="מתי להזכיר?",
        reply_markup=get_reminder_keyboard()
    )
    return REMINDER



async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    now = get_now()
    reminder_time = None
    
    if choice == REMINDER_CUSTOM:
        await query.edit_message_text(
            "⏰ הקלד זמן תזכורת:\n"
            "<b>HH:MM</b> — להיום (או מחר אם עבר)\n"
            "<b>DD/MM HH:MM</b> — לתאריך מסוים\n\n"
            "(שלח /cancel לביטול)",
            parse_mode='HTML'
        )
        return WAITING_CUSTOM_REMINDER

    if choice == REMINDER_1H:
        reminder_time = now + timedelta(hours=1)
    elif choice == REMINDER_TONIGHT:
        reminder_time = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if reminder_time < now:
             reminder_time += timedelta(days=1)
    elif choice == REMINDER_TOMORROW:
        reminder_time = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    elif choice == REMINDER_3D:
        reminder_time = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=3)
    elif choice == REMINDER_1W:
        reminder_time = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(weeks=1)
    elif choice == REMINDER_NONE:
        reminder_time = None

    session = SessionLocal()
    try:
        if reminder_time:
            reminder_time_naive = to_naive_israel(reminder_time)
        else:
            reminder_time_naive = None

        new_task = Task(
            chat_id=update.effective_chat.id,
            text=context.user_data['description'],
            priority=context.user_data['priority'],
            parent_category=context.user_data['parent'],
            sub_category=context.user_data['subcategory'],
            reminder_time=reminder_time_naive,
            status='pending'
        )
        session.add(new_task)
        session.commit()
        session.refresh(new_task)

        if reminder_time:
            add_reminder_job(new_task.id, reminder_time, update.effective_chat.id)

        time_str = reminder_time.strftime('%H:%M %d/%m') if reminder_time else "ללא"
        await query.edit_message_text(
            f"✅ **המשימה נשמרה**\n"
            f"📝 {new_task.text}\n"
            f"⏰ תזכורת: {time_str}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error saving task: {e}")
        await query.edit_message_text("❌ ארעה שגיאה בשמירת המשימה.")
    finally:
        session.close()

    return ConversationHandler.END

async def custom_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles free-text time input for custom reminders during task creation."""
    text = update.message.text
    reminder_time, error = parse_custom_time(text)

    if error:
        await update.message.reply_text(
            f"❌ {error}\n\n"
            "שלח <b>HH:MM</b> או <b>DD/MM HH:MM</b>\n"
            "(או /cancel לביטול)",
            parse_mode='HTML'
        )
        return WAITING_CUSTOM_REMINDER

    session = SessionLocal()
    try:
        reminder_time_naive = to_naive_israel(reminder_time)
        new_task = Task(
            chat_id=update.effective_chat.id,
            text=context.user_data['description'],
            priority=context.user_data['priority'],
            parent_category=context.user_data['parent'],
            sub_category=context.user_data['subcategory'],
            reminder_time=reminder_time_naive,
            status='pending'
        )
        session.add(new_task)
        session.commit()
        session.refresh(new_task)

        add_reminder_job(new_task.id, reminder_time, update.effective_chat.id)

        time_str = reminder_time.strftime('%H:%M %d/%m')
        await update.message.reply_text(
            f"✅ <b>המשימה נשמרה</b>\n"
            f"📝 {new_task.text}\n"
            f"⏰ תזכורת: {time_str}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error saving task with custom reminder: {e}")
        await update.message.reply_text("❌ ארעה שגיאה בשמירת המשימה.")
    finally:
        session.close()

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('פעולה בוטלה.')
    return ConversationHandler.END

async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        tasks = session.query(Task).filter(
            Task.chat_id == update.effective_chat.id,
            Task.status == 'pending'
        ).all()
        
        if not tasks:
            msg = "אין משימות פתוחות! 🎉"
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.edit_message_text(msg)
            return

        # Sort: Urgent, Normal, Low
        priority_order = {'urgent': 0, 'normal': 1, 'low': 2}
        tasks.sort(key=lambda t: priority_order.get(t.priority, 99))

        # Group data by Parent -> Sub
        grouped = {CATEGORY_HOME: {}, CATEGORY_WORK: {}}
        for t in tasks:
            parent = t.parent_category if t.parent_category in grouped else None
            if not parent: continue 
            
            sub = t.sub_category or "כללי"
            if sub not in grouped[parent]:
                grouped[parent][sub] = []
            grouped[parent][sub].append(t)

        text_lines = ["📋 <b>המשימות שלך:</b>\n"]
        keyboard = []

        def add_section(parent_key, label, icon):
            sub_cats = grouped.get(parent_key, {})
            # Check if there are any tasks in this parent category
            if not any(sub_cats.values()):
                return False

            total_tasks = sum(len(l) for l in sub_cats.values())
            text_lines.append(f"{icon} <b>{label}</b> ({total_tasks})")
            keyboard.append([InlineKeyboardButton(f"{icon} {label}", callback_data="ignore")])
            
            for sub_name, section_tasks in sub_cats.items():
                if not section_tasks: continue
                
                text_lines.append(f"   📂 <i>{sub_name}</i>")
                keyboard.append([InlineKeyboardButton(f"   📂 {sub_name}", callback_data="ignore")])
                
                for t in section_tasks:
                    p_icon = "🔴" if t.priority == 'urgent' else "🟡" if t.priority == 'normal' else "🟢"
                    # Add to text
                    text_lines.append(f"      • {p_icon} {t.text}")
                    # Add to keyboard
                    keyboard.append([InlineKeyboardButton(f"      {p_icon} {t.text}", callback_data=f"{VIEW_TASK}{t.id}")])
            
            text_lines.append("") # Empty line
            return True

        has_home = add_section(CATEGORY_HOME, "בית", "🏠")
        
        if has_home and any(grouped[CATEGORY_WORK].values()):
             keyboard.append([InlineKeyboardButton("➖➖➖➖➖➖", callback_data="ignore")])

        add_section(CATEGORY_WORK, "עבודה", "💼")

        text_lines.append("💡 <i>לחץ על משימה לפרטים נוספים</i>")
        final_text = "\n".join(text_lines)
        markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text(final_text, reply_markup=markup, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.edit_message_text(final_text, reply_markup=markup, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        if update.message:
            await update.message.reply_text("❌ שגיאה בשליפת המשימות.")
    finally:
        session.close()

async def view_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.replace(VIEW_TASK, ""))
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id, Task.chat_id == update.effective_chat.id).first()
        if not task:
            await query.edit_message_text("❌ המשימה לא נמצאה (אולי נמחקה?)")
            return

        priority_map = {'urgent': "durgent 🔴", 'normal': "רגיל 🟡", 'low': "נמוך 🟢"}
        p_text = priority_map.get(task.priority, task.priority)
        time_str = task.reminder_time.strftime('%d/%m %H:%M') if task.reminder_time else "ללא"
        
        text = (
            f"📝 <b>{task.text}</b>\n"
            f"📂 קטגוריה: {task.parent_category} > {task.sub_category}\n"
            f"⚡ עדיפות: {p_text}\n"
            f"⏰ תזכורת: {time_str}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ סיים", callback_data=f"{DONE_TASK}{task.id}"),
                InlineKeyboardButton("✏️ ערוך פרטים", callback_data=f"{EDIT_TASK}{task.id}")
            ],
            [InlineKeyboardButton("⏰ ערוך תזכורת", callback_data=f"{EDIT_REMINDER_PREFIX}{task.id}")],
            [InlineKeyboardButton("🔙 חזרה לרשימה", callback_data="back_to_list")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    finally:
        session.close()

async def mark_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.replace(DONE_TASK, ""))
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id, Task.chat_id == update.effective_chat.id).first()
        if task:
            task.status = 'done'
            session.commit()
            await query.answer("המשימה סומנה כבוצעה! 🎉")
            # Return to list
            await list_tasks_command(update, context)
        else:
             await query.answer("המשימה לא נמצאה")
    finally:
        session.close()

async def edit_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.replace(EDIT_TASK, ""))
    context.user_data['editing_task_id'] = task_id
    
    await query.edit_message_text(
        "✏️ <b>הקלד את התיאור החדש של המשימה:</b>\n\n(שלח /cancel לביטול)",
        parse_mode='HTML'
    )
    return EDITING_DESCRIPTION

async def save_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.get('editing_task_id')
    new_text = update.message.text
    
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id, Task.chat_id == update.effective_chat.id).first()
        if task:
            task.text = new_text
            session.commit()
            await update.message.reply_text("✅ התיאור עודכן בהצלחה!")
            
            # Show the updated task view manually (cant edit message from here easily without sending new menu)
            # We will just show the main list again
            await list_tasks_command(update, context)
        else:
            await update.message.reply_text("❌ המשימה לא נמצאה.")
    finally:
        session.close()
    
    return ConversationHandler.END

async def back_to_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await list_tasks_command(update, context)

async def global_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies to any message not handled by other handlers to confirm connectivity."""
    logger.info(f"Received message: {update.message.text}")
    await update.message.reply_text("I heard you (Global Fallback)")

async def filter_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"Filtering task with data: {data}")
    
    # We can reuse list_tasks_command but we need to inject the filter into user_data or pass it?
    # list_tasks_command reads from DB directly.
    # Let's cheat slightly and modify user_data['filter'] then call a shared internal function,
    # OR simpler: just implement a dedicated filtered view here reusing the logic.
    
    target_category = CATEGORY_HOME if data == 'filter_home' else CATEGORY_WORK
    category_label = "בית" if target_category == CATEGORY_HOME else "עבודה"
    
    session = SessionLocal()
    try:
        tasks = session.query(Task).filter(
            Task.chat_id == update.effective_chat.id,
            Task.status == 'pending',
            Task.parent_category == target_category
        ).all()
        
        # Sort simple
        priority_order = {'urgent': 0, 'normal': 1, 'low': 2}
        tasks.sort(key=lambda t: priority_order.get(t.priority, 99))
        
        # Group by sub
        grouped = {}
        for t in tasks:
            sub = t.sub_category or "כללי"
            if sub not in grouped: grouped[sub] = []
            grouped[sub].append(t)
            
        icon_main = "🏠" if target_category == CATEGORY_HOME else "💼"
        text_lines = [f"🔎 <b>סינון: {icon_main} {category_label}</b> ({len(tasks)})", ""]
        keyboard = []
        
        # Back button
        keyboard.append([InlineKeyboardButton("🔙 חזרה לדשבורד", callback_data="list_tasks_dashboard")]) # pointing to list logic? No, wait.
        # "list_tasks_dashboard" mapped to list_tasks_command (full list). 
        # Ideally we want back to DASHBOARD.
        # Let's add that Button.
        
        for sub_name, section_tasks in grouped.items():
            text_lines.append(f"📂 <i>{sub_name}</i>")
            # keyboard.append([InlineKeyboardButton(f"📂 {sub_name}", callback_data="ignore")])
            for t in section_tasks:
                p_icon = "🔴" if t.priority == 'urgent' else "🟡" if t.priority == 'normal' else "🟢"
                text_lines.append(f"   • {p_icon} {t.text}")
                keyboard.append([InlineKeyboardButton(f"{p_icon} {t.text}", callback_data=f"{VIEW_TASK}{t.id}")])
            text_lines.append("")

        if not tasks:
            text_lines.append("<i>אין משימות בקטגוריה זו.</i>")
            
        final_text = "\n".join(text_lines)
        
        # Add a clear Back to Start
        keyboard.append([InlineKeyboardButton("🔙 חזרה לראשי", callback_data="back_to_dashboard")])
        
        await query.edit_message_text(final_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    finally:
        session.close()

async def back_to_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from src.bot.dashboard_handlers import dashboard_command
    await dashboard_command(update, context)

async def snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Don't want loading state
    
    # format: snooze_1h_123
    try:
        task_id = int(query.data.replace(SNOOZE_1H_PREFIX, ""))
    except ValueError:
        return
        
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id, Task.chat_id == update.effective_chat.id).first()
        if task:
            # new_time is aware
            new_time = get_now() + timedelta(hours=1)
            
            # Save naive to DB
            task.reminder_time = to_naive_israel(new_time)
            session.commit()
            
            # Reschedule with aware time
            add_reminder_job(task.id, new_time, update.effective_chat.id)
            
            await query.edit_message_text(f"💤 התזכורת נדחתה לשעה {new_time.strftime('%H:%M')}")
        else:
            await query.edit_message_text("❌ המשימה לא נמצאה")
    finally:
        session.close()

async def edit_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        task_id = int(query.data.replace(EDIT_REMINDER_PREFIX, ""))
    except ValueError:
        return
        
    await query.edit_message_text(
        text="⏰ **בחר זמן תזכורת חדש:**",
        reply_markup=get_reminder_keyboard(task_id=task_id),
        parse_mode='Markdown'
    )

async def update_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    # data format: upd_rem_<task_id>_<type>
    prefix_len = len(UPD_REMINDER_PREFIX)
    rest = data[prefix_len:]
    
    # We expect integer id then underscore then type string.
    # But reminder constants are strings like 'reminder_1h'.
    # Example: 123_reminder_1h
    
    # Split by first underscore ONLY to separate ID from Choice
    try:
        task_id_str, choice = rest.split('_', 1)
        task_id = int(task_id_str)
        # Adding back the prefix or just using the choice string?
        # choice should resolve to one of the constants, e.g. "reminder_1h"
    except ValueError:
         logger.error(f"Failed to parse update reminder data: {data}")
         return

    now = get_now()
    reminder_time = None

    # Logic copied from reminder_callback but reused
    if choice == REMINDER_1H:
        reminder_time = now + timedelta(hours=1)
    elif choice == REMINDER_TONIGHT:
        reminder_time = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if reminder_time < now:
             reminder_time += timedelta(days=1)
    elif choice == REMINDER_TOMORROW:
        reminder_time = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    elif choice == REMINDER_3D:
        reminder_time = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=3)
    elif choice == REMINDER_1W:
        reminder_time = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(weeks=1)
    elif choice == REMINDER_NONE:
        reminder_time = None

    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id, Task.chat_id == update.effective_chat.id).first()
        if task:
            task.reminder_time = to_naive_israel(reminder_time) if reminder_time else None
            session.commit()

            # Reschedule
            if reminder_time:
                add_reminder_job(task.id, reminder_time, update.effective_chat.id)
            else:
                # Ideally remove job but add_reminder_job with upsert should handle new ones. To remove we need remove_job logic which we dont have exposed yet easily.
                # However we can just let old job fail or overwrite if ID is same? 
                # add_reminder_job uses scheduler.add_job(..., replace_existing=True).
                # If we pass None date it might error.
                # If reminder is None we should probably TRY to remove the job from scheduler if possible, or do nothing.
                pass
            
            time_str = reminder_time.strftime('%H:%M %d/%m') if reminder_time else "ללא"
            await query.edit_message_text(f"✅ התזכורת עודכנה ל: {time_str}")
            
            # Show task view again after short delay? or leave as is.
            # Let's show filtered list or task view?
            # User might want to go back.
            # But we edited the message text so the buttons are gone.
            # Add a back button
            kb = [[InlineKeyboardButton("🔙 חזרה למשימה", callback_data=f"{VIEW_TASK}{task_id}")]]
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
            
        else:
            await query.edit_message_text("❌ המשימה לא נמצאה")
    finally:
        session.close()

async def custom_edit_reminder_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for custom time input when editing an existing task's reminder."""
    query = update.callback_query
    await query.answer()

    data = query.data
    prefix_len = len(UPD_REMINDER_PREFIX)
    rest = data[prefix_len:]
    try:
        task_id_str, _ = rest.split('_', 1)
        task_id = int(task_id_str)
    except ValueError:
        return ConversationHandler.END

    context.user_data['custom_reminder_task_id'] = task_id
    await query.edit_message_text(
        "⏰ הקלד זמן תזכורת:\n"
        "<b>HH:MM</b> — להיום (או מחר אם עבר)\n"
        "<b>DD/MM HH:MM</b> — לתאריך מסוים\n\n"
        "(שלח /cancel לביטול)",
        parse_mode='HTML'
    )
    return WAITING_CUSTOM_REMINDER

async def custom_edit_reminder_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles free-text time input when editing an existing task's reminder."""
    text = update.message.text
    reminder_time, error = parse_custom_time(text)

    if error:
        await update.message.reply_text(
            f"❌ {error}\n\n"
            "שלח <b>HH:MM</b> או <b>DD/MM HH:MM</b>\n"
            "(או /cancel לביטול)",
            parse_mode='HTML'
        )
        return WAITING_CUSTOM_REMINDER

    task_id = context.user_data.get('custom_reminder_task_id')
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id, Task.chat_id == update.effective_chat.id).first()
        if task:
            task.reminder_time = to_naive_israel(reminder_time)
            session.commit()
            add_reminder_job(task.id, reminder_time, update.effective_chat.id)

            time_str = reminder_time.strftime('%H:%M %d/%m')
            kb = [[InlineKeyboardButton("🔙 חזרה למשימה", callback_data=f"{VIEW_TASK}{task_id}")]]
            await update.message.reply_text(
                f"✅ התזכורת עודכנה ל: {time_str}",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await update.message.reply_text("❌ המשימה לא נמצאה")
    finally:
        session.close()

    return ConversationHandler.END

async def quick_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return

    session = SessionLocal()
    try:
        new_task = Task(
            chat_id=update.effective_chat.id,
            text=text,
            priority='normal', # Default
            parent_category=CATEGORY_HOME, # Default to Home
            sub_category='כללי',
            reminder_time=None,
            status='pending'
        )
        session.add(new_task)
        session.commit()
        await update.message.reply_text(f"✅ משימה מהירה נוספה: **{text}**", parse_mode='Markdown')
        
        # Optionally show dashboard again?
        from src.bot.dashboard_handlers import dashboard_command
        await dashboard_command(update, context)
        
    except Exception as e:
        logger.error(f"Error quick add: {e}")
        await update.message.reply_text("❌ שגיאה בהוספה מהירה")
    finally:
        session.close()
    
    return ConversationHandler.END
