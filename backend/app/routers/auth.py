import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel,Field
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import create_access_token
from app.models.base import User

router = APIRouter(prefix="/auth", tags=["auth"])

class OTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$", description="Must be exactly 10 digits")

class OTPVerify(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$")
    code: str = Field(..., min_length=6, max_length=6)

@router.post("/otp")
async def request_otp(payload: OTPRequest):
    # Generate 6-digit OTP
    otp_code = str(random.randint(100000, 999999))
    
    # Store in Redis with 5-minute (300s) TTL
    await redis_client.setex(f"otp:{payload.phone}", 300, otp_code)
    
    # SIMULATE SMS: Print to console instead of using a real provider
    print(f"\n{'='*40}\n🚀 SMS SIMULATION: OTP for {payload.phone} is {otp_code}\n{'='*40}\n")
    
    return {"message": "OTP sent"}

@router.post("/verify")
async def verify_otp(payload: OTPVerify, db: AsyncSession = Depends(get_db)):
    cached_otp = await redis_client.get(f"otp:{payload.phone}")
    
    if not cached_otp or cached_otp != payload.code:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
    # Clear the OTP so it can't be reused
    await redis_client.delete(f"otp:{payload.phone}")

    # Find or create user
    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(phone=payload.phone)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Generate JWT
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_id": str(user.id)
    }