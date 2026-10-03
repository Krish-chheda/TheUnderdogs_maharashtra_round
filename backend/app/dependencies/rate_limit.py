import time
from fastapi import Request, HTTPException
from app.core.redis import redis_client 

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1]) or capacity
local ts = tonumber(data[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * refill)
if tokens < 1 then return 0 end
redis.call('HMSET', key, 'tokens', tokens - 1, 'ts', now)
redis.call('EXPIRE', key, 120)
return 1
"""

def rate_limit(name: str, capacity: int, refill: float):
    async def dep(request: Request):
        # Fallback to IP address for rate limiting
        client_ip = request.client.host if request.client else "127.0.0.1"
        key = f"rl:{name}:{client_ip}"
        
        # Execute Lua script atomically
        ok = await redis_client.eval(TOKEN_BUCKET_LUA, 1, key, capacity, refill, time.time())
        if not ok:
            raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
            
    return dep