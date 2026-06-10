"""Configuration loader for the calorie tracking bot."""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(var_name: str) -> str:
    """Get a required environment variable or raise an error."""
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value


# Telegram
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")

# Webhook URL (your Vercel deployment URL, e.g. https://your-app.vercel.app)
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

# AI Model (OpenAI-compatible aggregator)
API_KEY: str = _require("API_KEY")
API_BASE_URL: str = _require("API_BASE_URL")
MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o")
VISION_MODEL_NAME: str = os.getenv("VISION_MODEL_NAME", MODEL_NAME)

# Database (Supabase Postgres connection string)
DATABASE_URL: str = _require("DATABASE_URL")

# Upstash Redis (rate limiting) — shared engine, central config + kill switch
# Accept both Upstash-default (REST_) and short names for dashboard copy-paste compat
UPSTASH_REDIS_URL: str = os.getenv("UPSTASH_REDIS_REST_URL", os.getenv("UPSTASH_REDIS_URL", ""))
UPSTASH_REDIS_TOKEN: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", os.getenv("UPSTASH_REDIS_TOKEN", ""))
# Fallback limit for the single "est" bucket when central config is absent.
RATE_LIMIT_EST_MAX: int = int(os.getenv("RATE_LIMIT_EST_MAX", "5"))
RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", str(5 * 24 * 60 * 60)))

# Optional: comma-separated Telegram user IDs allowed to use the bot.
_authorized_raw = os.getenv("AUTHORIZED_TELEGRAM_IDS", "")
if _authorized_raw:
    try:
        AUTHORIZED_TELEGRAM_IDS = [int(x.strip()) for x in _authorized_raw.split(",") if x.strip()]
    except ValueError:
        raise ValueError("AUTHORIZED_TELEGRAM_IDS must be a comma-separated list of integers")
else:
    AUTHORIZED_TELEGRAM_IDS = []

# Whitelist toggle
REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "True").lower() == "true"
