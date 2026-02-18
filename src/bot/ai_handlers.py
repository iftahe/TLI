import os
import asyncio
import tempfile
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from src.bot.utils import get_now, to_naive_israel, ISRAEL_TZ
from src.bot.constants import CATEGORY_HOME, CATEGORY_WORK
from src.database.core import SessionLocal
from src.database.models import Task
from src.scheduler.service import add_reminder_job

logger = logging.getLogger(__name__)

# Local states (no conflict — existing states: 0-3, 10-12, 20)
AI_WAITING_TEXT = 30
AI_CONFIRM = 31

# Callback data
AI_CONFIRM_SAVE = "ai_confirm_save"
AI_CONFIRM_CANCEL = "ai_confirm_cancel"

_PRIORITY_LABELS = {"urgent": "דחוף 🔴", "normal": "רגיל 🟡", "low": "נמוך 🟢"}
_CATEGORY_LABELS = {"home": "🏠 בית", "work": "💼 עבודה", "projects": "📁 פרויקטים"}


async def _show_ai_confirmation(message, result):
    """Build and show AI task confirmation message with Save/Cancel buttons."""
    pri_label = _PRIORITY_LABELS.get(result["priority"], result["priority"])
    cat_label = _CATEGORY_LABELS.get(result["parent_category"], result["parent_category"])

    if result["reminder_time"]:
        try:
            dt = datetime.fromisoformat(result["reminder_time"])
            time_str = dt.strftime("%H:%M %d/%m")
        except ValueError:
            time_str = "ללא"
    else:
        time_str = "ללא"

    sub_cat = result.get("sub_category", "כללי")

    msg = (
        f"🤖 <b>אישור משימה מ-AI</b>\n\n"
        f"📝 {result['description']}\n"
        f"📂 {cat_label}"
    )
    if result["parent_category"] == "projects" and sub_cat != "כללי":
        msg += f" > {sub_cat}"
    msg += f"\n⚡ {pri_label}\n"
    msg += f"⏰ תזכורת: {time_str}\n\n"
    msg += "לשמור את המשימה?"

    keyboard = [
        [
            InlineKeyboardButton("✅ שמור", callback_data=AI_CONFIRM_SAVE),
            InlineKeyboardButton("❌ בטל", callback_data=AI_CONFIRM_CANCEL),
        ]
    ]

    await message.edit_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /ai command."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await update.message.reply_text(
            "⚠️ שירות ה-AI לא מוגדר. פנה למנהל המערכת."
        )
        return ConversationHandler.END

    # Check if inline text was provided: /ai לקנות חלב
    text = update.message.text
    # Remove the /ai prefix
    rest = text[3:].strip() if len(text) > 3 else ""

    if rest:
        return await _process_ai_text(update, context, rest, api_key)

    await update.message.reply_text(
        "🤖 שלח טקסט חופשי — אני יכול ליצור משימה או לענות על שאלות לגבי המשימות שלך.\n"
        "לדוגמה: <i>לקנות חלב מחר בבוקר</i>\n"
        "או: <i>כמה משימות דחופות יש לי?</i>\n\n"
        "(שלח /cancel לביטול)",
        parse_mode="HTML",
    )
    context.user_data["ai_api_key"] = api_key
    return AI_WAITING_TEXT


async def ai_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives free text in the two-step flow."""
    api_key = context.user_data.get("ai_api_key")
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await update.message.reply_text("⚠️ שירות ה-AI לא מוגדר.")
        return ConversationHandler.END

    return await _process_ai_text(update, context, update.message.text, api_key)


async def _process_ai_text(update, context, text, api_key):
    """Call Gemini and show confirmation or direct answer."""
    from src.services.ai import parse_task_from_text

    # Show processing indicator
    processing_msg = await update.message.reply_text("🤖 מעבד...")

    chat_id = update.effective_chat.id
    # Call Gemini in a thread to avoid blocking
    result = await asyncio.to_thread(parse_task_from_text, text, api_key, chat_id)

    if not result:
        await processing_msg.edit_text(
            "❌ לא הצלחתי לפרש את הטקסט. נסה לנסח אחרת."
        )
        return ConversationHandler.END

    if result.get("intent") == "TASK_QUERY":
        await processing_msg.edit_text(f"🤖 {result['response']}")
        return ConversationHandler.END

    context.user_data["ai_task"] = result
    await _show_ai_confirmation(processing_msg, result)
    return AI_CONFIRM


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages: download, transcribe via Gemini, create task."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await update.message.reply_text(
            "⚠️ שירות ה-AI לא מוגדר. פנה למנהל המערכת."
        )
        return ConversationHandler.END

    processing_msg = await update.message.reply_text("🎙️ מעבד הודעה קולית...")

    voice = update.message.voice
    chat_id = update.effective_chat.id
    tmp_path = None
    try:
        file = await voice.get_file()
        tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        tmp_path = tmp.name
        tmp.close()
        await file.download_to_drive(tmp_path)
        logger.info(f"Voice file downloaded: {tmp_path} ({voice.duration}s)")

        from src.services.ai import parse_task_from_voice
        result = await asyncio.to_thread(parse_task_from_voice, tmp_path, api_key, chat_id=chat_id)
    except Exception as e:
        logger.error(f"Voice processing error: {e}", exc_info=True)
        await processing_msg.edit_text("❌ שגיאה בעיבוד ההודעה הקולית.")
        return ConversationHandler.END
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if not result:
        await processing_msg.edit_text(
            "❌ לא הצלחתי לפרש את ההודעה הקולית. נסה שוב."
        )
        return ConversationHandler.END

    if result.get("intent") == "TASK_QUERY":
        await processing_msg.edit_text(f"🤖 {result['response']}")
        return ConversationHandler.END

    context.user_data["ai_task"] = result
    await _show_ai_confirmation(processing_msg, result)
    return AI_CONFIRM


async def ai_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle save/cancel confirmation."""
    query = update.callback_query
    await query.answer()

    action = query.data

    if action == AI_CONFIRM_CANCEL:
        context.user_data.pop("ai_task", None)
        context.user_data.pop("ai_api_key", None)
        await query.edit_message_text("❌ המשימה בוטלה.")
        return ConversationHandler.END

    # Save the task
    task_data = context.user_data.get("ai_task")
    if not task_data:
        await query.edit_message_text("❌ לא נמצאו נתוני משימה. נסה שוב.")
        return ConversationHandler.END

    # Parse reminder time
    reminder_time = None
    reminder_time_naive = None
    if task_data.get("reminder_time"):
        try:
            dt = datetime.fromisoformat(task_data["reminder_time"])
            # Make it timezone-aware in Israel time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ISRAEL_TZ)
            reminder_time = dt
            reminder_time_naive = to_naive_israel(dt)
        except (ValueError, TypeError):
            pass

    session = SessionLocal()
    try:
        new_task = Task(
            chat_id=update.effective_chat.id,
            text=task_data["description"],
            priority=task_data["priority"],
            parent_category=task_data["parent_category"],
            sub_category=task_data.get("sub_category", "כללי"),
            reminder_time=reminder_time_naive,
            status="pending",
            is_shared=0,
        )
        session.add(new_task)
        session.commit()
        session.refresh(new_task)

        if reminder_time:
            add_reminder_job(new_task.id, reminder_time, update.effective_chat.id)

        time_str = reminder_time.strftime("%H:%M %d/%m") if reminder_time else "ללא"
        cat_label = _CATEGORY_LABELS.get(task_data["parent_category"], "")
        await query.edit_message_text(
            f"✅ <b>המשימה נשמרה</b>\n"
            f"📝 {new_task.text}\n"
            f"📂 {cat_label}\n"
            f"⏰ תזכורת: {time_str}",
            parse_mode="HTML",
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving AI task: {e}", exc_info=True)
        await query.edit_message_text("❌ שגיאה בשמירת המשימה.")
    finally:
        session.close()

    context.user_data.pop("ai_task", None)
    context.user_data.pop("ai_api_key", None)
    return ConversationHandler.END


async def ai_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback /cancel handler for AI conversation."""
    context.user_data.pop("ai_task", None)
    context.user_data.pop("ai_api_key", None)
    await update.message.reply_text("פעולה בוטלה.")
    return ConversationHandler.END
