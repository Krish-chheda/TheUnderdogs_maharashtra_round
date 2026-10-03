import os
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings

REDIS_URL = settings.REDIS_URL
redis_client = redis.from_url(REDIS_URL, decode_responses=True)