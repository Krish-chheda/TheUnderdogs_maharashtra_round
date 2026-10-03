import os
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

# Connects to your local Redis instance
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)