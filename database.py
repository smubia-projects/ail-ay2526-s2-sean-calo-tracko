"""Postgres database layer for the calorie tracking bot (Supabase via asyncpg)."""

import asyncpg
from datetime import datetime, timedelta
from typing import Optional

from config import DATABASE_URL


async def _get_conn() -> asyncpg.Connection:
    # Disable statement cache for pgbouncer compatibility
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


# ─── User CRUD ───────────────────────────────────────────────────────────────


async def get_user(telegram_id: int) -> Optional[dict]:
    """Get user profile by Telegram ID."""
    conn = await _get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def ensure_user_exists(telegram_id: int, name: str = "") -> None:
    """Create a minimal users row if one doesn't exist (satisfies FK constraints)."""
    conn = await _get_conn()
    try:
        await conn.execute(
            "INSERT INTO users (telegram_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            telegram_id, name,
        )
    finally:
        await conn.close()


async def upsert_user(telegram_id: int, **fields) -> None:
    """Create or update a user profile."""
    from datetime import timezone
    fields["updated_at"] = datetime.now(timezone.utc)
    existing = await get_user(telegram_id)

    conn = await _get_conn()
    try:
        if existing:
            set_clause = ", ".join(
                f"{k} = ${i + 2}" for i, k in enumerate(fields.keys())
            )
            values = [telegram_id] + list(fields.values())
            await conn.execute(
                f"UPDATE users SET {set_clause} WHERE telegram_id = $1",
                *values,
            )
        else:
            fields["telegram_id"] = telegram_id
            cols = ", ".join(fields.keys())
            placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
            await conn.execute(
                f"INSERT INTO users ({cols}) VALUES ({placeholders})",
                *fields.values(),
            )
    finally:
        await conn.close()


# ─── Meal Logging ────────────────────────────────────────────────────────────


async def log_meal(
    user_id: int,
    name: str,
    description: str,
    calories: int,
    protein_g: float = 0,
    carbs_g: float = 0,
    fat_g: float = 0,
) -> int:
    """Log a meal and return its ID."""
    conn = await _get_conn()
    try:
        row = await conn.fetchrow(
            """INSERT INTO meals (user_id, name, description, calories, protein_g, carbs_g, fat_g)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            user_id, name, description, calories, protein_g, carbs_g, fat_g,
        )
        return row["id"]
    finally:
        await conn.close()


async def get_meals_for_date(user_id: int, sgt_date: datetime) -> list[dict]:
    """
    Get all meals for a specific SGT date.
    Maps the SGT day (00:00 to 23:59) to UTC boundaries for the database query.
    """
    from datetime import timezone
    # 2026-03-03 00:00:00 SGT
    sgt_start = sgt_date.replace(hour=0, minute=0, second=0, microsecond=0)
    # Convert SGT 00:00 to UTC (SGT = UTC+8, so UTC = SGT-8)
    utc_start = sgt_start - timedelta(hours=8)
    utc_start = utc_start.replace(tzinfo=timezone.utc)
    
    utc_end = utc_start + timedelta(days=1) - timedelta(microseconds=1)

    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            """SELECT * FROM meals
               WHERE user_id = $1 AND logged_at BETWEEN $2 AND $3
               ORDER BY logged_at""",
            user_id, utc_start, utc_end,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_meals_for_week(user_id: int, sgt_end_date: datetime) -> dict[str, list[dict]]:
    """Get meals grouped by date for the past 7 days (SGT)."""
    from datetime import timezone
    # sgt_end_date is today SGT. We want 7 days including today.
    # Start of today SGT
    sgt_today_start = sgt_end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    # Start of 7 days ago SGT
    sgt_week_start = sgt_today_start - timedelta(days=6)
    
    # Convert SGT week start to UTC
    utc_start = sgt_week_start - timedelta(hours=8)
    utc_start = utc_start.replace(tzinfo=timezone.utc)
    
    # End of today SGT
    utc_end = (sgt_today_start + timedelta(days=1)) - timedelta(hours=8) - timedelta(microseconds=1)
    utc_end = utc_end.replace(tzinfo=timezone.utc)

    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            """SELECT * FROM meals
               WHERE user_id = $1 AND logged_at BETWEEN $2 AND $3
               ORDER BY logged_at""",
            user_id, utc_start, utc_end,
        )
    finally:
        await conn.close()

    result: dict[str, list[dict]] = {}
    for i in range(7):
        day = (sgt_week_start + timedelta(days=i)).strftime("%Y-%m-%d")
        result[day] = []

    for row in rows:
        d = dict(row)
        # Convert UTC logged_at to SGT for correct grouping
        logged_at_utc = d["logged_at"].replace(tzinfo=timezone.utc)
        logged_at_sgt = logged_at_utc + timedelta(hours=8)
        day = logged_at_sgt.strftime("%Y-%m-%d")
        if day in result:
            result[day].append(d)

    return result


async def delete_meal(meal_id: int, user_id: int) -> bool:
    """Delete a meal by ID. Returns True if deleted."""
    conn = await _get_conn()
    try:
        result = await conn.execute(
            "DELETE FROM meals WHERE id = $1 AND user_id = $2",
            meal_id, user_id,
        )
        return result == "DELETE 1"
    finally:
        await conn.close()


# ─── Saved Meals ─────────────────────────────────────────────────────────────


async def save_meal(
    user_id: int,
    name: str,
    description: str,
    calories: int,
    protein_g: float = 0,
    carbs_g: float = 0,
    fat_g: float = 0,
) -> int:
    """Save a meal template and return its ID."""
    conn = await _get_conn()
    try:
        row = await conn.fetchrow(
            """INSERT INTO saved_meals (user_id, name, description, calories, protein_g, carbs_g, fat_g)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            user_id, name, description, calories, protein_g, carbs_g, fat_g,
        )
        return row["id"]
    finally:
        await conn.close()


async def get_saved_meals(user_id: int) -> list[dict]:
    """Get all saved meals for a user."""
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            "SELECT * FROM saved_meals WHERE user_id = $1 ORDER BY name",
            user_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_saved_meal(meal_id: int, user_id: int) -> Optional[dict]:
    """Get a specific saved meal."""
    conn = await _get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM saved_meals WHERE id = $1 AND user_id = $2",
            meal_id, user_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def delete_saved_meal(meal_id: int, user_id: int) -> bool:
    """Delete a saved meal by ID. Returns True if deleted."""
    conn = await _get_conn()
    try:
        result = await conn.execute(
            "DELETE FROM saved_meals WHERE id = $1 AND user_id = $2",
            meal_id, user_id,
        )
        return result == "DELETE 1"
    finally:
        await conn.close()


async def get_users_with_reminder(hour: int) -> list[int]:
    """Get telegram_ids of users with reminders enabled at the given hour."""
    conn = await _get_conn()
    try:
        rows = await conn.fetch(
            "SELECT telegram_id FROM users WHERE reminder_enabled = 1 AND reminder_hour = $1",
            hour,
        )
        return [r["telegram_id"] for r in rows]
    finally:
        await conn.close()
