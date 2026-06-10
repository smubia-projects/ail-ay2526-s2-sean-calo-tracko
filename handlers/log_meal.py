"""Handler for meal logging via image or text, with refinement flow."""

import json
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from ai_service import estimate_calories_from_text, estimate_calories_from_image, refine_estimate
from database import log_meal, save_meal, get_meals_for_date, get_user
from rate_limit import check_estimate_limit
from utils import format_estimate_message, format_progress_bar, MENU_BUTTONS_REGEX, get_now_sgt

PAUSED_MSG = (
    "⏸️ *Demo paused*\n\n"
    "This demo is temporarily paused. Please check back soon!"
)

_RATE_LIMIT_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("Join AI Lodge", url="https://www.smubia.com/ai-lodge")],
    [InlineKeyboardButton("View source on GitHub", url="https://github.com/smubia-projects/ail-ay2526-s2-sean-calo-tracko")],
    [InlineKeyboardButton("Explore other projects", url="https://www.smubia.com/showcase")],
])


async def _estimate_limit_blocked(update: Update) -> bool:
    """Reply with the right notice and return True if this AI estimate is blocked."""
    state, limit = check_estimate_limit(update.effective_user.id)
    if state == "killed":
        await update.message.reply_text(PAUSED_MSG, parse_mode="Markdown")
        return True
    if state == "limited":
        msg = (
            "⚠️ *Rate limit reached*\n\n"
            "🍽️ *You've tasted the full experience!*\n"
            f"You've used all {limit} free AI estimates included with this demo. "
            "Want to keep going? Self-host your own copy or join AI Lodge "
            "to build projects like this!"
        )
        await update.message.reply_text(
            msg, parse_mode="Markdown", reply_markup=_RATE_LIMIT_BUTTONS,
        )
        return True
    return False

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOOD, WAITING_ACTION, WAITING_REFINE, WAITING_SAVE_NAME = range(4)


def _build_action_keyboard() -> InlineKeyboardMarkup:
    """Build the inline keyboard for meal estimate actions."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Log", callback_data="meal_log"),
                InlineKeyboardButton("💾 Save & Log", callback_data="meal_save"),
            ],
            [
                InlineKeyboardButton("✏️ Refine", callback_data="meal_refine"),
                InlineKeyboardButton("❌ Cancel", callback_data="meal_cancel"),
            ],
        ]
    )


async def init_log_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Invoked when user taps '🍱 Log Meal' button."""
    await update.message.reply_text(
        "📝 *What did you eat?*\n\n"
        "Please describe your meal (e.g., '1 burger and small fries') "
        "or send a photo of your food.",
        parse_mode="Markdown",
    )
    return WAITING_FOOD


async def handle_food_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a food photo sent by the user."""
    if await _estimate_limit_blocked(update):
        return ConversationHandler.END
    msg = await update.message.reply_text("📸 Analyzing your food photo... ⏳")

    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        caption = update.message.caption or ""
        estimate = await estimate_calories_from_image(bytes(image_bytes), caption)

        context.user_data["current_estimate"] = estimate
        await msg.edit_text(
            format_estimate_message(estimate),
            parse_mode="Markdown",
            reply_markup=_build_action_keyboard(),
        )
        return WAITING_ACTION

    except ValueError as e:
        await msg.edit_text(f"❌ {str(e)}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error processing food photo: {e}", exc_info=True)
        await msg.edit_text(
            "❌ Sorry, I couldn't analyze that image. Please try again or "
            "send a text description instead."
        )
        return ConversationHandler.END


async def handle_food_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a text description of food."""
    text = update.message.text.strip()
    logger.info(f"Food text received: '{text}'")

    if not text:
        return ConversationHandler.END

    if await _estimate_limit_blocked(update):
        return ConversationHandler.END

    msg = await update.message.reply_text("🔍 Estimating calories... ⏳")

    try:
        estimate = await estimate_calories_from_text(text)
        context.user_data["current_estimate"] = estimate

        await msg.edit_text(
            format_estimate_message(estimate),
            parse_mode="Markdown",
            reply_markup=_build_action_keyboard(),
        )
        return WAITING_ACTION

    except ValueError as e:
        await msg.edit_text(f"❌ {str(e)}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error estimating from text: {e}", exc_info=True)
        await msg.edit_text(
            "❌ Sorry, I couldn't estimate the calories. Please try again."
        )
        return ConversationHandler.END


async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button presses on the estimate message."""
    query = update.callback_query
    await query.answer()
    action = query.data

    estimate = context.user_data.get("current_estimate")
    if not estimate:
        await query.edit_message_text("⚠️ Session expired. Please send your food again.")
        return ConversationHandler.END

    if action == "meal_log":
        # Log the meal
        await log_meal(
            user_id=update.effective_user.id,
            name=estimate["name"],
            description=estimate.get("description", ""),
            calories=estimate["calories"],
            protein_g=estimate.get("protein_g", 0),
            carbs_g=estimate.get("carbs_g", 0),
            fat_g=estimate.get("fat_g", 0),
        )
        # Fetch daily total
        user_id = update.effective_user.id
        user = await get_user(user_id)
        today_meals = await get_meals_for_date(user_id, get_now_sgt())
        total_cal = sum(m["calories"] for m in today_meals)
        goal = (user.get("daily_calorie_goal") or 2000) if user else 2000
        remaining = max(goal - total_cal, 0)

        await query.edit_message_text(
            f"✅ *Logged:* {estimate['name']} — {estimate['calories']} kcal\n\n"
            f"📊 *Today:* {total_cal} / {goal} kcal\n"
            f"{format_progress_bar(total_cal, goal)}\n"
            f"{'💡 ' + str(remaining) + ' kcal remaining' if remaining > 0 else '⚠️ ' + str(total_cal - goal) + ' kcal over goal'}",
            parse_mode="Markdown",
        )
        context.user_data.pop("current_estimate", None)
        return ConversationHandler.END

    elif action == "meal_save":
        await query.edit_message_text(
            f"💾 *Save Meal*\n\n"
            f"Enter a name for this meal (e.g., \"Morning oatmeal\"):",
            parse_mode="Markdown",
        )
        return WAITING_SAVE_NAME

    elif action == "meal_refine":
        await query.edit_message_text(
            f"✏️ *Refine Estimate*\n\n"
            f"Current: {estimate['name']} — {estimate['calories']} kcal\n\n"
            f"Provide additional details to improve the estimate.\n"
            f"Examples:\n"
            f"• \"It was a large portion\"\n"
            f"• \"No oil or butter was used\"\n"
            f"• \"There were 3 eggs, not 2\"\n"
            f"• \"It also included a side of rice\"",
            parse_mode="Markdown",
        )
        return WAITING_REFINE

    elif action == "meal_cancel":
        await query.edit_message_text("❌ Cancelled.")
        context.user_data.pop("current_estimate", None)
        return ConversationHandler.END

    return WAITING_ACTION


async def handle_refine_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle additional details for refining the estimate."""
    feedback = update.message.text.strip()
    estimate = context.user_data.get("current_estimate")

    if not estimate:
        await update.message.reply_text("⚠️ Session expired. Please send your food again.")
        return ConversationHandler.END

    if await _estimate_limit_blocked(update):
        return ConversationHandler.END

    msg = await update.message.reply_text("🔄 Re-estimating with your feedback... ⏳")

    try:
        refined = await refine_estimate(estimate, feedback)
        context.user_data["current_estimate"] = refined

        # Show comparison
        diff = refined["calories"] - estimate["calories"]
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        comparison = f"\n📊 _Changed by {diff_str} kcal from previous estimate_\n"

        await msg.edit_text(
            format_estimate_message(refined) + comparison,
            parse_mode="Markdown",
            reply_markup=_build_action_keyboard(),
        )
        return WAITING_ACTION

    except ValueError as e:
        await msg.edit_text(f"❌ {str(e)}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error refining estimate: {e}")
        await msg.edit_text(
            "❌ Error refining. Showing original estimate.",
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            format_estimate_message(estimate),
            parse_mode="Markdown",
            reply_markup=_build_action_keyboard(),
        )
        return WAITING_ACTION


async def handle_save_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the name input for saving a meal."""
    meal_name = update.message.text.strip()
    estimate = context.user_data.get("current_estimate")

    if not estimate:
        await update.message.reply_text("⚠️ Session expired. Please send your food again.")
        return ConversationHandler.END

    # Save the meal template
    await save_meal(
        user_id=update.effective_user.id,
        name=meal_name,
        description=estimate.get("description", ""),
        calories=estimate["calories"],
        protein_g=estimate.get("protein_g", 0),
        carbs_g=estimate.get("carbs_g", 0),
        fat_g=estimate.get("fat_g", 0),
    )

    # Also log it
    await log_meal(
        user_id=update.effective_user.id,
        name=meal_name,
        description=estimate.get("description", ""),
        calories=estimate["calories"],
        protein_g=estimate.get("protein_g", 0),
        carbs_g=estimate.get("carbs_g", 0),
        fat_g=estimate.get("fat_g", 0),
    )

    # Fetch daily total
    user_id = update.effective_user.id
    user = await get_user(user_id)
    today_meals = await get_meals_for_date(user_id, get_now_sgt())
    total_cal = sum(m["calories"] for m in today_meals)
    goal = (user.get("daily_calorie_goal") or 2000) if user else 2000
    remaining = max(goal - total_cal, 0)

    await update.message.reply_text(
        f"✅ *Saved & Logged:* {meal_name} — {estimate['calories']} kcal\n\n"
        f"📊 *Today:* {total_cal} / {goal} kcal\n"
        f"{format_progress_bar(total_cal, goal)}\n"
        f"{'💡 ' + str(remaining) + ' kcal remaining' if remaining > 0 else '⚠️ ' + str(total_cal - goal) + ' kcal over goal'}\n\n"
        f"Use /saved to quickly log this meal again!",
        parse_mode="Markdown",
    )
    context.user_data.pop("current_estimate", None)
    return ConversationHandler.END


async def cancel_logging(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel meal logging and show help."""
    from utils import send_help_message
    await send_help_message(update, context)
    context.user_data.pop("current_estimate", None)
    return ConversationHandler.END





def get_handler():
    """Return the ConversationHandler for meal logging."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🍱 Log Meal$"), init_log_meal),
            MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_food_photo),
            # Also support a direct command if they prefer
            CommandHandler("log", init_log_meal),
        ],
        states={
            WAITING_FOOD: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_food_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_food_text),
            ],
            WAITING_ACTION: [
                CallbackQueryHandler(handle_action, pattern=r"^meal_"),
            ],
            WAITING_REFINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_refine_input),
            ],
            WAITING_SAVE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_save_name),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_logging),
            MessageHandler(filters.COMMAND, cancel_logging),
            # If they type random text (not a menu button), end the conversation so help shows
            MessageHandler(filters.TEXT & (~filters.Regex(MENU_BUTTONS_REGEX)), cancel_logging),
        ],
        per_message=False,
        allow_reentry=True,
    )
