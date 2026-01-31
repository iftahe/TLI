import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.bot.constants import *

logger = logging.getLogger(__name__)

def get_shared_choice_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("👤 אישי", callback_data=SHARED_TASK_NO),
            InlineKeyboardButton("👥 משותף", callback_data=SHARED_TASK_YES),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

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

def get_subcategory_keyboard(parent_category, chat_id=None, is_shared=False):
    last_exc = None
    for attempt in range(1, 4):
        start = time.monotonic()
        session = SessionLocal()
        try:
            if is_shared:
                from src.database.core import ensure_shared_categories
                ensure_shared_categories(session)
                categories = session.query(SubCategory).filter(
                    SubCategory.parent == parent_category,
                    SubCategory.is_active == 1,
                    SubCategory.chat_id == 0
                ).all()
            else:
                if chat_id:
                    ensure_user_categories(session, chat_id)
                categories = session.query(SubCategory).filter(
                    SubCategory.parent == parent_category,
                    SubCategory.is_active == 1,
                    SubCategory.chat_id == chat_id
                ).all()

            buttons = []
            row = []
            for cat in categories:
                row.append(InlineKeyboardButton(cat.name, callback_data=f'sub_{cat.id}'))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)

            if not buttons:
                buttons.append([InlineKeyboardButton("אין קטגוריות", callback_data='sub_none')])

            elapsed = time.monotonic() - start
            logger.info(f"get_subcategory_keyboard: loaded {len(categories)} categories (attempt {attempt}, {elapsed:.2f}s)")
            return InlineKeyboardMarkup(buttons)
        except Exception as e:
            elapsed = time.monotonic() - start
            last_exc = e
            logger.warning(f"get_subcategory_keyboard: attempt {attempt} failed ({elapsed:.2f}s): {e}")
            session.close()
            if attempt < 3:
                time.sleep(1.0 * attempt)  # 1s, 2s — allows Neon cold start to complete
            continue
        finally:
            session.close()

    logger.error("get_subcategory_keyboard: all 3 attempts failed", exc_info=last_exc)
    raise last_exc

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
        [InlineKeyboardButton("אחר ✍️", callback_data=get_cb(REMINDER_CUSTOM))],
        [InlineKeyboardButton("עוד 3 ימים 🗓️", callback_data=get_cb(REMINDER_3D))],
        [InlineKeyboardButton("עוד שבוע 📅", callback_data=get_cb(REMINDER_1W))],
        [InlineKeyboardButton("ללא 🔕", callback_data=get_cb(REMINDER_NONE))],
    ]
    return InlineKeyboardMarkup(keyboard)
