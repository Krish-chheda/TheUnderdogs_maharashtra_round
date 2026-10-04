import os
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings

REDIS_URL = settings.REDIS_URL
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Additional imports for bot‑test progress tracking
import json
import uuid
from datetime import datetime, timezone

async def set_bot_test_progress(test_id: str, data: dict) -> None:
    """Store bot‑test progress in Redis under a namespaced key.
    The data dict is stored as a hash; callers should include any relevant fields
    (e.g., status, started_at, finished_at, progress, result_json, error).
    """
    key = f"bot_test:{test_id}"
    # Ensure datetime objects are serialized as ISO strings
    for k, v in data.items():
        if isinstance(v, datetime):
            data[k] = v.isoformat()
    await redis_client.hset(key, mapping=data)
    # Keep the data for 24 hours by default
    await redis_client.expire(key, 86400)

async def get_bot_test_progress(test_id: str) -> dict:
    """Retrieve stored bot‑test progress.
    Returns a dict of the stored fields, converting ISO timestamps back to datetime.
    """
    key = f"bot_test:{test_id}"
    raw = await redis_client.hgetall(key)
    # Convert timestamp strings back to datetime where appropriate
    for k in ["started_at", "finished_at"]:
        if k in raw:
            try:
                raw[k] = datetime.fromisoformat(raw[k])
            except Exception:
                pass
    return raw