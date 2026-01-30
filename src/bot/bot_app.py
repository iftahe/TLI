import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler, TypeHandler, ApplicationHandlerStop
from src.bot.handlers import *
from src.bot.constants import *
from src.bot.utils import is_user_allowed

logger = logging.getLogger(__name__)

async def auth_gate(update: Update, context):
    user = update.effective_user
    if user is None or not is_user_allowed(user.id):
        logger.warning(f"Unauthorized access attempt from user {user.id if user else 'unknown'}")
        if update.message:
            await update.message.reply_text("⛔ אין לך הרשאה להשתמש בבוט זה.")
        elif update.callback_query:
            await update.callback_query.answer("⛔ אין הרשאה", show_alert=True)
        raise ApplicationHandlerStop()

def create_app():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("No BOT_TOKEN in environment")

    app = ApplicationBuilder().token(token).build()

    # Auth gate — blocks all updates from unauthorized users (runs before all other handlers)
    app.add_handler(TypeHandler(Update, auth_gate), group=-1)

    # --- Conversation Handlers (registered first so they track state correctly) ---

    # Conversation for Editing
    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_task_callback, pattern=f"^{EDIT_TASK}")],
        states={
            EDITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(edit_conv)

    # Quick Add Conversation
    from src.bot.dashboard_handlers import dashboard_command, quick_add_callback

    qa_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(quick_add_callback, pattern="^quick_add_btn$")],
        states={
            "QUICK_ADD_WAITING": [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_add_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(qa_conv)

    # Main task creation conversation — pattern filters prevent stealing unrelated callbacks
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^(בית|עבודה)'), task_entry_handler)],
        states={
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_handler)],
            PRIORITY: [CallbackQueryHandler(priority_callback, pattern=f"^({PRIORITY_URGENT}|{PRIORITY_NORMAL}|{PRIORITY_LOW})$")],
            SUB_CATEGORY: [CallbackQueryHandler(subcategory_callback, pattern=r"^sub_")],
            REMINDER: [CallbackQueryHandler(reminder_callback, pattern=r"^reminder_")],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)

    # Categories Management
    from src.bot.category_handlers import (
        categories_command, add_category_callback, save_new_category,
        delete_category_callback, cancel_category_op,
        WAITING_NEW_CATEGORY_NAME, ADD_CAT_PREFIX, DEL_CAT_PREFIX
    )

    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_category_callback, pattern=f"^{ADD_CAT_PREFIX}")],
        states={
            WAITING_NEW_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_category)]
        },
        fallbacks=[CommandHandler('cancel', cancel_category_op)]
    )
    app.add_handler(cat_conv)

    # --- Command Handlers ---
    app.add_handler(CommandHandler('list', list_tasks_command))
    app.add_handler(CommandHandler(['start', 'dashboard'], dashboard_command))
    app.add_handler(CommandHandler('categories', categories_command))

    # --- Callback Query Handlers (standalone, pattern-matched) ---

    # List actions
    app.add_handler(CallbackQueryHandler(view_task_callback, pattern=f"^{VIEW_TASK}"))
    app.add_handler(CallbackQueryHandler(mark_done_callback, pattern=f"^{DONE_TASK}"))
    app.add_handler(CallbackQueryHandler(back_to_list_callback, pattern="^back_to_list$"))

    # Dashboard navigation
    app.add_handler(CallbackQueryHandler(list_tasks_command, pattern="^list_tasks_dashboard$"))
    app.add_handler(CallbackQueryHandler(back_to_dashboard_callback, pattern="^back_to_dashboard$"))
    app.add_handler(CallbackQueryHandler(filter_tasks_callback, pattern="^(filter_home|filter_work)$"))

    # Snooze & Reminder editing
    app.add_handler(CallbackQueryHandler(snooze_callback, pattern=f"^{SNOOZE_1H_PREFIX}"))
    app.add_handler(CallbackQueryHandler(edit_reminder_handler, pattern=f"^{EDIT_REMINDER_PREFIX}"))
    app.add_handler(CallbackQueryHandler(update_reminder_handler, pattern=f"^{UPD_REMINDER_PREFIX}"))

    # Category delete
    app.add_handler(CallbackQueryHandler(delete_category_callback, pattern=f"^{DEL_CAT_PREFIX}"))

    # Global fallback for debugging (must be last)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), global_fallback))

    return app
