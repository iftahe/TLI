from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.database.core import SessionLocal, ensure_user_categories
from src.database.models import SubCategory
from src.bot.constants import CATEGORY_HOME, CATEGORY_WORK
import logging

logger = logging.getLogger(__name__)

# States for Category Management
WAITING_NEW_CATEGORY_NAME = 20

# Callbacks
ADD_CAT_PREFIX = "add_cat_"
DEL_CAT_PREFIX = "del_cat_"
DELETE_CONFIRM = "confirm_del_"

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all categories with Add/Delete options."""
    session = SessionLocal()
    try:
        chat_id = update.effective_chat.id
        ensure_user_categories(session, chat_id)
        categories = session.query(SubCategory).filter(
            SubCategory.chat_id == chat_id,
            SubCategory.is_active == 1
        ).all()
        
        home_cats = [c for c in categories if c.parent == CATEGORY_HOME]
        work_cats = [c for c in categories if c.parent == CATEGORY_WORK]
        
        keyboard = []
        
        # Home Section
        keyboard.append([InlineKeyboardButton("🏠 בית", callback_data="ignore")])
        for c in home_cats:
            keyboard.append([
                InlineKeyboardButton(c.name, callback_data="ignore"),
                InlineKeyboardButton("❌ מחק", callback_data=f"{DEL_CAT_PREFIX}{c.id}")
            ])
        keyboard.append([InlineKeyboardButton("➕ הוסף לבית", callback_data=f"{ADD_CAT_PREFIX}{CATEGORY_HOME}")])
        
        # Spacer
        keyboard.append([InlineKeyboardButton("➖➖➖➖", callback_data="ignore")])

        # Work Section
        keyboard.append([InlineKeyboardButton("💼 עבודה", callback_data="ignore")])
        for c in work_cats:
            keyboard.append([
                InlineKeyboardButton(c.name, callback_data="ignore"),
                InlineKeyboardButton("❌ מחק", callback_data=f"{DEL_CAT_PREFIX}{c.id}")
            ])
        keyboard.append([InlineKeyboardButton("➕ הוסף לעבודה", callback_data=f"{ADD_CAT_PREFIX}{CATEGORY_WORK}")])

        msg = "📂 **ניהול קטגוריות**\nלחץ על 'הוסף' ליצירת קטגוריה חדשה, או 'מחק' להסרה."
        markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(msg, reply_markup=markup, parse_mode='Markdown')
        elif update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=markup, parse_mode='Markdown')
            
    finally:
        session.close()

async def add_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parent = query.data.replace(ADD_CAT_PREFIX, "")
    context.user_data['new_cat_parent'] = parent
    
    await query.edit_message_text(
        f"📝 אנא הקלד את שם הקטגוריה החדשה עבור **{parent}**:\n(שלח /cancel לביטול)",
        parse_mode='Markdown'
    )
    return WAITING_NEW_CATEGORY_NAME

async def save_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parent = context.user_data.get('new_cat_parent')
    
    session = SessionLocal()
    try:
        new_cat = SubCategory(name=text, parent=parent, chat_id=update.effective_chat.id, is_active=1)
        session.add(new_cat)
        session.commit()
        await update.message.reply_text(f"✅ הקטגוריה **{text}** נוספה בהצלחה!", parse_mode='Markdown')
        
        # Show list again
        await categories_command(update, context)
    except Exception as e:
        logger.error(f"Error adding category: {e}")
        await update.message.reply_text("❌ שגיאה בהוספת הקטגוריה.")
    finally:
        session.close()
    
    return ConversationHandler.END

async def delete_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cat_id = int(query.data.replace(DEL_CAT_PREFIX, ""))
    logger.info(f"Attempting to delete category {cat_id}")
    session = SessionLocal()
    try:
        cat = session.query(SubCategory).filter(SubCategory.id == cat_id, SubCategory.chat_id == update.effective_chat.id).first()
        if cat:
            logger.info(f"Found category {cat.name} (ID: {cat.id}), marking as inactive.")
            cat.is_active = 0
            session.commit()
            await query.answer("הקטגוריה נמחקה")
            await categories_command(update, context)
        else:
            logger.warning(f"Category ID {cat_id} not found.")
            await query.answer("לא נמצא")
    except Exception as e:
        logger.error(f"Error deleting category {cat_id}: {e}", exc_info=True)
        await query.answer("שגיאה במחיקה")
    finally:
        session.close()

async def cancel_category_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("פעולה בוטלה.")
    await categories_command(update, context)
    return ConversationHandler.END
