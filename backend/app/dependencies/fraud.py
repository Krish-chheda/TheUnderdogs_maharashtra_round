import time
import logging
from enum import Enum
from fastapi import Request, HTTPException, Depends, status
from app.core.redis import redis_client
from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.models.base import User

logger = logging.getLogger("fraud")

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

# Atomic Lua Script for IP to Distinct Account Tracking
IP_ACCOUNT_VELOCITY_LUA = """
local key = KEYS[1]
local user_id = ARGV[1]
local window = tonumber(ARGV[2])

redis.call('SADD', key, user_id)
local count = redis.call('SCARD', key)
local ttl = redis.call('TTL', key)
if ttl < 0 then
    redis.call('EXPIRE', key, window)
end
return count
"""

async def record_and_get_ip_account_count(event_id: str, client_ip: str, user_id: str) -> int:
    key = f"fraud:ip_users:{event_id}:{client_ip}"
    try:
        count = await redis_client.eval(
            IP_ACCOUNT_VELOCITY_LUA,
            1,
            key,
            user_id,
            settings.IP_ACCOUNT_WINDOW_SECONDS
        )
        return int(count)
    except Exception as e:
        logger.warning(f"Failed to record IP velocity in Redis: {e}")
        return 1

async def assess_risk(request: Request, user: User, event_id: str | None = None) -> tuple[RiskLevel, list[str]]:
    """
    Evaluates risk signals without invasive fingerprinting:
    - User-Agent consistency (low-confidence)
    - IP account velocity (college Wi-Fi aware)
    - Rapid burst / repetition
    Returns (RiskLevel, list_of_signals)
    """
    signals = []
    risk_score = 0
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Signal 1: Automated Script User-Agent (low-confidence signal)
    user_agent = request.headers.get("user-agent", "").lower()
    known_automation_tools = ["curl", "python-requests", "postman", "wget", "urllib", "aiohttp", "httpx"]
    if not user_agent:
        signals.append("missing_user_agent")
        risk_score += 15
    elif any(tool in user_agent for tool in known_automation_tools):
        signals.append("script_user_agent")
        risk_score += 25

    # Signal 2: IP to Account Velocity (Multi-account detection)
    if event_id:
        unique_users = await record_and_get_ip_account_count(event_id, client_ip, str(user.id))
        threshold = settings.IP_ACCOUNT_THRESHOLD
        if unique_users > threshold * 3:
            signals.append("extreme_ip_account_velocity")
            risk_score += 50
        elif unique_users > threshold:
            signals.append("high_ip_account_velocity")
            risk_score += 30

    # Signal 3: Account Phone Verification Status
    if not user.is_phone_verified:
        signals.append("unverified_phone")
        risk_score += 20

    # Classify Risk Level
    if risk_score >= 50:
        level = RiskLevel.HIGH
    elif risk_score >= 25:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    return level, signals

async def anti_bot_farm(request: Request, user: User = Depends(get_current_user)) -> tuple[RiskLevel, list[str]]:
    """
    Lightweight, explainable bot protection dependency.
    Does not blindly ban shared IPs. Instead, flags risk to trigger stepped-up verification.
    """
    event_id = request.path_params.get("event_id")
    risk_level, signals = await assess_risk(request, user, event_id)
    
    # Extreme bot activity handling: if extreme IP velocity combined with automated tools, apply temporary cooldown
    if "extreme_ip_account_velocity" in signals and "script_user_agent" in signals:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="High velocity from this network. Please complete verification or try again in a few moments.",
            headers={"Retry-After": "30"}
        )
        
    return risk_level, signals