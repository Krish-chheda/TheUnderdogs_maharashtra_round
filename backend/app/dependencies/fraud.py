from fastapi import Request, HTTPException, Depends
from app.core.redis import redis_client
from app.dependencies.auth import get_current_user
from app.models.base import User

async def anti_bot_farm(request: Request, user: User = Depends(get_current_user)):
    # 1. Block basic scripts and missing User-Agents
    user_agent = request.headers.get("user-agent", "").lower()
    blocked_agents = ["curl", "python-requests", "postman", "wget", "urllib"]
    
    if not user_agent or any(bot in user_agent for bot in blocked_agents):
        raise HTTPException(status_code=403, detail="Automated scripts are not allowed.")

    # 2. IP to Account Velocity (Bot Farm Detection)
    client_ip = request.client.host if request.client else "127.0.0.1"
    event_id = request.path_params.get("event_id")
    
    if event_id:
        # Key specific to the event and the IP address
        key = f"fraud:ip_users:{event_id}:{client_ip}"
        
        # Add this user's ID to a Redis Set (Sets automatically handle duplicates)
        await redis_client.sadd(key, str(user.id))
        await redis_client.expire(key, 3600)  # Keep record for 1 hour
        
        # Count how many unique users are on this IP
        unique_users = await redis_client.scard(key)
        
        # If more than 3 different accounts use the same IP, block the request
        if unique_users > 3:
            raise HTTPException(
                status_code=403, 
                detail="Fraud alert: Too many accounts originating from this IP address."
            )