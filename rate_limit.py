"""Rate-limit adapter for CalorieBot.

Uses the shared rate-limit engine (event mode + kill switch + central config).
Telegram has no request IP to key on, so we call the engine's `status()` directly
with a per-user identity instead of `enforce()` — see
DOCS/shared/rate-limit/central-config.md §9.
"""

from __future__ import annotations

from typing import Optional

from rate_limit_engine import RateLimiter
import config

# Single bucket: all AI estimate calls (text / image / refine) share one allowance,
# matching the bot's original behaviour. Slug = full project folder name.
limiter = RateLimiter(
    project="ail-ay2526-s2-sean-calo-tracko",
    buckets={"est": config.RATE_LIMIT_EST_MAX},
    redis_url=config.UPSTASH_REDIS_URL,
    redis_token=config.UPSTASH_REDIS_TOKEN,
    default_window=config.RATE_LIMIT_WINDOW_SECONDS,
)


def check_estimate_limit(telegram_user_id: int) -> tuple[str, Optional[int]]:
    """Return the rate-limit state for an AI estimate by this Telegram user.

    -> ('ok', None)        request may proceed
    -> ('limited', max)    user is over their allowance
    -> ('killed', None)    the demo is paused via the central kill switch
    """
    return limiter.status(f"tg:{telegram_user_id}", "est")
