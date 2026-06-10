"""Handler for /start command."""

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import CommandHandler, ContextTypes

from auth import require_authorized

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🍱 Log Meal")],
        [KeyboardButton("📊 Today"), KeyboardButton("📈 Week")],
        [KeyboardButton("📋 Saved"), KeyboardButton("👤 Profile")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


@require_authorized
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with bot overview."""
    welcome = (
        "👋 *Welcome to CalorieBot!*\n\n"
        "I help you track your daily calorie intake using AI.\n"
        "Just send me a *photo* or *text description* of your food "
        "and I'll estimate the calories and macros!\n\n"
        "📋 *Commands:*\n"
        "🍱 /log — Log a meal (text or photo)\n"
        "📊 /today — Check today's progress\n"
        "📈 /week — See weekly history\n"
        "👤 /profile — View or update your settings\n"
        "📋 /saved — Browse your saved meals\n"
        "🎯 /goal — View or set your calorie goal\n"
        "📜 /history — View a past date\n"
        "🔔 /reminder — Set meal reminders"
    )
    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=MENU_KEYBOARD
    )


def get_handler():
    """Return the handler for registration."""
    return CommandHandler("start", start_command)
