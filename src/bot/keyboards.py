from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.bot.constants import *

def get_priority_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("דחוף 🔴", callback_data=PRIORITY_URGENT),
            InlineKeyboardButton("רגיל 🟡", callback_data=PRIORITY_NORMAL),
            InlineKeyboardButton("נמוך 🟢", callback_data=PRIORITY_LOW),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

from src.database.core import SessionLocal, ensure_user_categories
from src.database.models import SubCategory

def get_subcategory_keyboard(parent_category, chat_id=None):
    session = SessionLocal()
    try:
        if chat_id:
            ensure_user_categories(session, chat_id)
        categories = session.query(SubCategory).filter(
            SubCategory.parent == parent_category,
            SubCategory.is_active == 1,
            SubCategory.chat_id == chat_id
        ).all()
        
        buttons = []
        # Group in pairs if possible
        row = []
        for cat in categories:
            # We use name as value for now for backward compatibility or ID? 
            # Let's use ID to be robust: 'sub_ID'
            row.append(InlineKeyboardButton(cat.name, callback_data=f'sub_{cat.id}'))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
            
        if not buttons:
            buttons.append([InlineKeyboardButton("אין קטגוריות", callback_data='sub_none')])
            
        return InlineKeyboardMarkup(buttons)
    finally:
        session.close()

def get_reminder_keyboard(task_id=None):
    # If task_id is provided, we use the update prefix: upd_rem_<task_id>_<type>
    # Otherwise we use the standard constants (for new task flow)
    
    def get_cb(res_type):
        if task_id:
            return f"{UPD_REMINDER_PREFIX}{task_id}_{res_type}"
        return res_type

    keyboard = [
        [InlineKeyboardButton("עוד שעה 🕐", callback_data=get_cb(REMINDER_1H))],
        [InlineKeyboardButton("הערב 20:00 🌙", callback_data=get_cb(REMINDER_TONIGHT))],
        [InlineKeyboardButton("מחר 09:00 ☀️", callback_data=get_cb(REMINDER_TOMORROW))],
        [InlineKeyboardButton("מחר 09:30 ☕", callback_data=get_cb(REMINDER_MORNING_930))],
        [InlineKeyboardButton("עוד 3 ימים 🗓️", callback_data=get_cb(REMINDER_3D))],
        [InlineKeyboardButton("עוד שבוע 📅", callback_data=get_cb(REMINDER_1W))],
        [InlineKeyboardButton("ללא 🔕", callback_data=get_cb(REMINDER_NONE))],
    ]
    return InlineKeyboardMarkup(keyboard)
