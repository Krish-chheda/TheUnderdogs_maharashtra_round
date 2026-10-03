import time
from fastapi import Request, HTTPException, status
from app.core.redis import redis_client
from app.core.config import settings

# Atomic Lua Token Bucket with Retry-After calculation
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4]) or 1

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    ts = now
else
    local elapsed = math.max(0, now - ts)
    tokens = math.min(capacity, tokens + (elapsed * refill))
    ts = now
end

if tokens < requested then
    local missing = requested - tokens
    local retry_after = math.ceil(missing / refill)
    if retry_after < 1 then retry_after = 1 end
    return {0, tostring(retry_after)}
end

tokens = tokens - requested
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
local ttl = math.ceil(capacity / refill) * 2
if ttl < 60 then ttl = 60 end
redis.call('EXPIRE', key, ttl)
return {1, "0"}
"""

def get_client_ip(request: Request) -> str:
    # Safely extract client IP
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

async def check_token_bucket(key: str, capacity: int, refill: float, requested: int = 1) -> None:
    now = time.time()
    try:
        res = await redis_client.eval(TOKEN_BUCKET_LUA, 1, key, capacity, refill, now, requested)
        if isinstance(res, (list, tuple)) and len(res) >= 2:
            allowed, retry_after = int(res[0]), str(res[1])
        else:
            allowed = int(res) if res is not None else 1
            retry_after = "1"
            
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": retry_after}
            )
    except HTTPException:
        raise
    except Exception as e:
        # If redis is unreachable or error occurs in dev/test, don't crash unless critical
        pass

def rate_limit(name: str, capacity: int | None = None, refill: float | None = None):
    """
    Standard IP-based rate limit dependency (backward compatible).
    """
    async def dep(request: Request):
        cap = capacity if capacity is not None else settings.RATE_LIMIT_JOIN_IP_CAPACITY
        ref = refill if refill is not None else settings.RATE_LIMIT_JOIN_IP_REFILL
        ip = get_client_ip(request)
        key = f"rl:{name}:ip:{ip}"
        await check_token_bucket(key, cap, ref)
    return dep

async def check_multi_dim_rate_limits(
    request: Request,
    scope: str,
    ip: str,
    user_id: str | None = None,
    event_id: str | None = None,
):
    """
    Evaluates multi-dimensional rate limits:
    - IP
    - User
    - Event + User
    - Event + IP
    """
    # 1. IP Dimension
    await check_token_bucket(
        f"rl:{scope}:ip:{ip}",
        settings.RATE_LIMIT_JOIN_IP_CAPACITY,
        settings.RATE_LIMIT_JOIN_IP_REFILL
    )
    
    # 2. Event + IP Dimension
    if event_id:
        await check_token_bucket(
            f"rl:{scope}:ev_ip:{event_id}:{ip}",
            settings.RATE_LIMIT_JOIN_EVENT_IP_CAPACITY,
            settings.RATE_LIMIT_JOIN_EVENT_IP_REFILL
        )
        
    # 3. User Dimension
    if user_id:
        await check_token_bucket(
            f"rl:{scope}:user:{user_id}",
            settings.RATE_LIMIT_JOIN_USER_CAPACITY,
            settings.RATE_LIMIT_JOIN_USER_REFILL
        )
        
        # 4. Event + User Dimension
        if event_id:
            await check_token_bucket(
                f"rl:{scope}:ev_user:{event_id}:{user_id}",
                settings.RATE_LIMIT_JOIN_EVENT_USER_CAPACITY,
                settings.RATE_LIMIT_JOIN_EVENT_USER_REFILL
            )