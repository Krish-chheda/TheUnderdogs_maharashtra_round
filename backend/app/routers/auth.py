import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.base import User

router = APIRouter(prefix="/auth", tags=["auth"])

class OTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$", description="Must be exactly 10 digits")

class OTPVerify(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$")
    code: str = Field(..., min_length=6, max_length=6)

class AuthCredentials(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=72)

class SignupRequest(AuthCredentials):
    role: str = "user"
    

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    if payload.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Role must be user or admin")

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=payload.email.lower(),
        password_hash=get_password_hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"message": "Account created", "user_id": str(user.id), "role": user.role}

@router.post("/login")
async def login(payload: AuthCredentials, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "role": user.role,
    }

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
        user = User(
            phone=payload.phone,
            email=f"{payload.phone}@otp.local",
            password_hash="",
        )
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