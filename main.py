"""CalorieBot — Application builder (shared by both webhook and polling modes)."""

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
from handlers import start, profile, log_meal, goal, tracking, saved_meals, reminder
from utils import MENU_BUTTONS_REGEX

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Welcome & help"),
    BotCommand("log", "Log a meal (text or photo)"),
    BotCommand("profile", "Set up or view your profile"),
    BotCommand("goal", "View or set calorie goal"),
    BotCommand("today", "Today's calorie summary"),
    BotCommand("week", "This week's summary"),
    BotCommand("history", "View a past day's calories"),
    BotCommand("saved", "Your saved meals"),
    BotCommand("reminder", "Meal reminder settings"),
]

BUTTON_MAP = {
    "📊 Today": tracking.today_command,
    "📈 Week": tracking.week_command,
    "📋 Saved": saved_meals.saved_command,
}


async def menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route menu button taps to the corresponding command handlers."""
    text = update.message.text.strip()
    handler_func = BUTTON_MAP.get(text)
    if handler_func:
        await handler_func(update, context)
        raise ApplicationHandlerStop()


async def post_init(application) -> None:
    """Run once after the application is initialized."""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot commands registered.")


def build_app():
    """Build and configure the PTB Application."""
    from auth import is_authorized
    from telegram.ext import CallbackQueryHandler

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # ── Global Authorization Check ──
    async def global_auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        if not await is_authorized(user.id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "🚫 *Access Denied*\n\nYou are not authorized to use this bot.",
                    parse_mode="Markdown",
                )
            elif update.callback_query:
                await update.callback_query.answer("Access denied.", show_alert=True)
            raise ApplicationHandlerStop()
        from database import ensure_user_exists
        await ensure_user_exists(user.id, user.full_name or "")

    app.add_handler(MessageHandler(filters.ALL, global_auth_check), group=-2)
    app.add_handler(CallbackQueryHandler(global_auth_check), group=-2)

    # ── Menu button handler ──
    button_filter = filters.Regex(MENU_BUTTONS_REGEX)
    app.add_handler(MessageHandler(button_filter, menu_button_handler), group=-1)

    # ── Register handlers ──
    app.add_handler(profile.get_handler())
    app.add_handler(log_meal.get_handler())
    app.add_handler(start.get_handler())
    app.add_handler(goal.get_handler())

    for handler in tracking.get_handlers():
        app.add_handler(handler)

    for handler in saved_meals.get_handlers():
        app.add_handler(handler)

    for handler in reminder.get_handlers():
        app.add_handler(handler)

    # ── Catch-all fallback ──
    async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        from utils import send_help_message
        await send_help_message(update, context)

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_message))

    return app


def main() -> None:
    """Run the bot in polling mode (for local development)."""
    app = build_app()
    logger.info("Bot starting in polling mode...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
