import asyncio
import logging
import os
import random
from datetime import datetime, timedelta
from telegram import Bot
from src.database.core import SessionLocal
from src.database.models import Task

logger = logging.getLogger(__name__)

async def send_message_async(chat_id, text, reply_markup=None):
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not found inside job")
        return
    async with Bot(token=token) as bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', reply_markup=reply_markup)

def send_reminder_job(task_id, chat_id):
    session = SessionLocal()
    try:
        task = session.query(Task).filter(Task.id == task_id).first()
        if task and task.status != 'done':
            logger.info(f"Sending reminder for task {task_id} to chat {chat_id}")
            text = f"⏰ <b>תזכורת למשימה:</b>\n{task.text}"

            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            from src.bot.constants import SNOOZE_1H_PREFIX, EDIT_TASK, VIEW_TASK

            keyboard = [
                [InlineKeyboardButton("💤 נודניק (1 שעה)", callback_data=f"{SNOOZE_1H_PREFIX}{task.id}")],
                [InlineKeyboardButton("✏️ ערוך/צפה", callback_data=f"{VIEW_TASK}{task.id}")]
            ]
            markup = InlineKeyboardMarkup(keyboard)

            asyncio.run(send_message_async(chat_id, text, reply_markup=markup))
            logger.info(f"Reminder sent successfully for task {task_id}")
        else:
            logger.info(f"Skipping reminder for task {task_id}: task not found or already done")
    except Exception as e:
        logger.error(f"Error in send_reminder_job for task {task_id}: {e}", exc_info=True)
    finally:
        session.close()

# Sarcastic opening hooks keyed by performance bracket
_BRIEFING_HOOKS = {
    'amazing': [  # completed > remaining
        "וואו, אתמול הייתם מכונת ביצוע! היום בוא נראה אם זה לא היה מקרי 🏆🎰",
        "אתמול סיימתם יותר ממה שנשאר — חשודים ביעילות. המשיכו ככה 🕵️✨",
        "מישהו שם קפה כפול אתמול? ביצועים מרשימים. היום אל תאכזבו 💪☕",
    ],
    'good': [  # completed >= 2 and completed >= remaining/2
        "אתמול הייתם בסדר גמור. לא גיבורי על, אבל גם לא אסון. ממוצע יציב 📊👍",
        "סיימתם כמה דברים אתמול — נחמד. היום יש הזדמנות להתקדם עוד 🚶‍♂️🌤️",
        "אתמול עבדתם, היום עובדים. החיים ממשיכים. בואו נראה מה יש 📋🫡",
    ],
    'meh': [  # completed == 1
        "אתמול סיימתם משימה אחת. אחת. נו, עדיף מאפס, נכון? 🤷‍♂️1️⃣",
        "משימה אחת אתמול? לפחות היה סימן חיים. היום אפשר לשפר 📈🐌",
        "אוקיי, אתמול לא היה היום הכי פרודוקטיבי. קורה. היום זה היום 🌅💫",
    ],
    'zero': [  # completed == 0, remaining > 0
        "אתמול? אפס. נאדה. כלום. בוא ננסה משהו חדש — לעשות דברים 🫠📭",
        "אתמול הייתם בחופשה מנטלית. היום חוזרים לעבודה, כן? 🏖️➡️💼",
        "אפס משימות אתמול. המשימות לא הולכות לשום מקום, הן מחכות בסבלנות 🧘‍♀️⏳",
        "יום אחד בלי אף סימון V. חלום של כל משימה — לחיות לנצח 🧟‍♂️📋",
    ],
    'clean': [  # no pending tasks at all
        "אין לכם אף משימה פתוחה. מה אתם, רובוטים? תהנו מהיום 🤖🎉",
        "רשימה ריקה. יום חופשי. אלא אם כן שכחתם להוסיף משהו 🤔🏝️",
    ],
}

def _get_briefing_hook(completed_yesterday, remaining_today):
    """Pick a sarcastic opening based on yesterday's performance."""
    if remaining_today == 0 and completed_yesterday == 0:
        return random.choice(_BRIEFING_HOOKS['clean'])
    if remaining_today == 0:
        return random.choice(_BRIEFING_HOOKS['clean'])
    if completed_yesterday == 0:
        return random.choice(_BRIEFING_HOOKS['zero'])
    if completed_yesterday == 1:
        return random.choice(_BRIEFING_HOOKS['meh'])
    if completed_yesterday > remaining_today:
        return random.choice(_BRIEFING_HOOKS['amazing'])
    return random.choice(_BRIEFING_HOOKS['good'])

def _age_indicator(created_at, now_naive):
    """Return age emoji: 🏛️ >7d, 🐢 >3d, empty otherwise."""
    if not created_at:
        return ""
    age = now_naive - created_at
    if age.days > 7:
        return " 🏛️"
    if age.days > 3:
        return " 🐢"
    return ""

def _format_task_line(task, now_naive):
    """Format a single task line for the briefing."""
    icon = "🔴" if task.priority == 'urgent' else "🟡" if task.priority == 'normal' else "🟢"
    age = _age_indicator(task.created_at, now_naive)
    return f"  {icon} {task.text}{age}"

# Sarcastic evening reflection hooks keyed by performance bracket
_EVENING_HOOKS = {
    'productive': [  # completed >= 5
        "יום פרודוקטיבי! סימנתם {count} משימות. מחר אפשר לנוח... או לא 💪🔥",
        "{count} משימות היום? מישהו רצה להרשים. הצלחתם 🏆",
        "וואלה, {count} משימות. אם ככה כל יום — תגמרו את הכל עד יום שישי 📈",
    ],
    'decent': [  # completed >= 2
        "סיימתם {count} משימות היום. לא רע, לא מדהים. יום רגיל של אנשים רגילים 👍",
        "{count} משימות מסומנות. ההתקדמות קיימת, גם אם לא דרמטית 🚶‍♂️",
        "יום סביר — {count} משימות ירדו מהרשימה. מחר ממשיכים 📋",
    ],
    'minimal': [  # completed == 1
        "משימה אחת. אחת בודדה. טוב, לפחות הראיתם שאתם חיים 🫠",
        "סימנתם משימה אחת היום. הרשימה שולחת תודה מעומק הלב 🙏",
        "1. אחד. יחיד. בודד. זה מה שהיה היום. מחר יותר? 🤞",
    ],
    'zero': [  # completed == 0
        "אפס משימות היום. הרשימה בדיוק כמו שהייתה בבוקר. קונסיסטנטיות! 🫡",
        "יום בלי אף V. המשימות חוגגות — עוד יום חיים 🎊📋",
        "היום? כלום. נאדה. אפס. מחר זה יום חדש. חדש! 🌅",
    ],
}

def _get_evening_reflection(completed_today, urgent_pending):
    """Pick a sarcastic evening reflection based on today's completions."""
    if completed_today >= 5:
        line = random.choice(_EVENING_HOOKS['productive']).format(count=completed_today)
    elif completed_today >= 2:
        line = random.choice(_EVENING_HOOKS['decent']).format(count=completed_today)
    elif completed_today == 1:
        line = random.choice(_EVENING_HOOKS['minimal'])
    else:
        line = random.choice(_EVENING_HOOKS['zero'])

    if urgent_pending > 0:
        line += f"\n⚠️ {urgent_pending} משימות דחופות עדיין פתוחות. רק אומר."

    return line


def evening_brief_job():
    """Send the 20:30 evening brief to each user."""
    from src.bot.utils import ALLOWED_USERS, get_now
    from src.services.weather import (
        get_tomorrow_forecast,
        format_clothing_recommendation,
        format_weather_line,
    )
    from src.services.calendar import (
        get_calendar_service,
        get_calendar_map,
        get_tomorrow_events,
        format_events_section,
    )

    session = SessionLocal()
    try:
        now = get_now()
        now_naive = now.replace(tzinfo=None)
        today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)

        # --- Weather (shared across all users) ---
        api_key = os.getenv("OPENWEATHER_API_KEY")
        weather_section = ""
        if api_key:
            forecast = get_tomorrow_forecast(api_key)
            if forecast:
                weather_section = (
                    format_clothing_recommendation(forecast) + "\n"
                    + format_weather_line(forecast) + "\n\n"
                )
            else:
                weather_section = "🌤️ שירות מזג האוויר לא זמין\n\n"

        # --- Calendar setup ---
        cal_service = get_calendar_service()
        cal_map = get_calendar_map()

        # --- Task reflection data ---
        completed_today_all = session.query(Task).filter(
            Task.status == 'done',
            Task.completed_at >= today_start,
            Task.completed_at <= now_naive,
        ).all()

        pending_urgent = session.query(Task).filter(
            Task.status == 'pending',
            Task.priority == 'urgent',
        ).all()

        user_completed = {}
        shared_completed = 0
        for t in completed_today_all:
            if t.is_shared:
                shared_completed += 1
            else:
                user_completed[t.chat_id] = user_completed.get(t.chat_id, 0) + 1

        user_urgent = {}
        shared_urgent = 0
        for t in pending_urgent:
            if t.is_shared:
                shared_urgent += 1
            else:
                user_urgent[t.chat_id] = user_urgent.get(t.chat_id, 0) + 1

        # All users to notify
        all_user_ids = set(user_completed.keys())
        if ALLOWED_USERS:
            all_user_ids.update(ALLOWED_USERS)

        for chat_id in all_user_ids:
            msg = f"🌙 <b>תדריך ערב</b> — {now_naive.strftime('%d/%m')}\n\n"

            # Weather (same for all)
            msg += weather_section

            # Calendar (per user)
            if cal_service and chat_id in cal_map:
                events = get_tomorrow_events(cal_service, cal_map[chat_id])
                if events is not None:
                    msg += format_events_section(events) + "\n\n"

            # Task reflection
            my_completed = user_completed.get(chat_id, 0) + shared_completed
            my_urgent = user_urgent.get(chat_id, 0) + shared_urgent
            msg += _get_evening_reflection(my_completed, my_urgent)

            msg += "\n\nלילה טוב 🌜"

            try:
                asyncio.run(send_message_async(chat_id, msg))
                logger.info(f"Evening brief sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send evening brief to chat {chat_id}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error in evening_brief_job: {e}", exc_info=True)
    finally:
        session.close()


def daily_briefing_job():
    from src.bot.utils import ALLOWED_USERS, get_now

    session = SessionLocal()
    try:
        now = get_now()
        now_naive = now.replace(tzinfo=None)

        # Yesterday boundaries (naive, Israel time)
        yesterday_start = (now_naive - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59)

        # All pending tasks
        pending = session.query(Task).filter(Task.status == 'pending').all()

        # Tasks completed yesterday
        completed_yesterday_all = session.query(Task).filter(
            Task.status == 'done',
            Task.completed_at >= yesterday_start,
            Task.completed_at <= yesterday_end
        ).all()

        # Separate shared vs personal pending
        shared_pending = [t for t in pending if t.is_shared and t.parent_category == 'home']
        personal_pending = [t for t in pending if not t.is_shared]

        # Build per-user personal task lists
        user_personal = {}
        for t in personal_pending:
            user_personal.setdefault(t.chat_id, []).append(t)

        # Completed yesterday per user + shared
        shared_completed = [t for t in completed_yesterday_all if t.is_shared]
        user_completed_count = {}
        for t in completed_yesterday_all:
            if not t.is_shared:
                user_completed_count[t.chat_id] = user_completed_count.get(t.chat_id, 0) + 1

        # All users who should get a briefing
        all_user_ids = set(user_personal.keys())
        if ALLOWED_USERS:
            all_user_ids.update(ALLOWED_USERS)

        # Add shared completed count to all users
        for uid in all_user_ids:
            user_completed_count.setdefault(uid, 0)
            user_completed_count[uid] += len(shared_completed)

        priority_order = {'urgent': 0, 'normal': 1, 'low': 2}

        for chat_id in all_user_ids:
            my_tasks = user_personal.get(chat_id, [])
            total_remaining = len(my_tasks) + len(shared_pending)

            # Quiet mode: skip if zero pending tasks
            if total_remaining == 0 and user_completed_count.get(chat_id, 0) == 0:
                continue

            completed_count = user_completed_count.get(chat_id, 0)
            hook = _get_briefing_hook(completed_count, total_remaining)

            # Sort by priority then age (oldest first within same priority)
            my_tasks.sort(key=lambda t: (priority_order.get(t.priority, 99), t.created_at or now_naive))
            shared_sorted = sorted(shared_pending, key=lambda t: (priority_order.get(t.priority, 99), t.created_at or now_naive))

            msg = f"☀️ <b>תדריך בוקר</b> — {now_naive.strftime('%d/%m')}\n\n"
            msg += f"{hook}\n\n"

            if completed_count > 0:
                msg += f"✅ אתמול סיימתם: <b>{completed_count}</b> משימות\n"
            msg += f"📌 נשאר היום: <b>{total_remaining}</b>\n\n"

            # Personal section (Rule of 3)
            if my_tasks:
                top_personal = my_tasks[:3]
                msg += f"👤 <b>המשימות שלי</b> ({len(my_tasks)})\n"
                for t in top_personal:
                    msg += _format_task_line(t, now_naive) + "\n"
                if len(my_tasks) > 3:
                    msg += f"  <i>...ועוד {len(my_tasks) - 3}</i>\n"
                msg += "\n"

            # Shared section (Rule of 3)
            if shared_sorted:
                top_shared = shared_sorted[:3]
                msg += f"👥 <b>המשימות המשותפות</b> ({len(shared_sorted)})\n"
                for t in top_shared:
                    msg += _format_task_line(t, now_naive) + "\n"
                if len(shared_sorted) > 3:
                    msg += f"  <i>...ועוד {len(shared_sorted) - 3}</i>\n"
                msg += "\n"

            if total_remaining == 0:
                msg += "🎉 <b>אין משימות פתוחות — יום חופשי!</b>\n"

            msg += "📲 /list לרשימה המלאה"

            try:
                asyncio.run(send_message_async(chat_id, msg))
                logger.info(f"Daily briefing sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send daily briefing to chat {chat_id}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error in daily_briefing_job: {e}", exc_info=True)
    finally:
        session.close()
