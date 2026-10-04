import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, get_password_hash, verify_password
from app.dependencies.rate_limit import check_token_bucket, get_client_ip
from app.models.base import User

logger = logging.getLogger("auth")
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
async def signup(request: Request, payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    client_ip = get_client_ip(request)
    await check_token_bucket(f"rl:signup:ip:{client_ip}", capacity=10, refill=0.5)

    if payload.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Role must be user or admin")

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=payload.email.lower(),
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        is_phone_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"message": "Account created", "user_id": str(user.id), "role": user.role}

@router.post("/login")
async def login(request: Request, payload: AuthCredentials, db: AsyncSession = Depends(get_db)):
    client_ip = get_client_ip(request)
    # Rate limit login by IP and email to prevent brute-forcing
    await check_token_bucket(
        f"rl:login:ip:{client_ip}",
        capacity=settings.RATE_LIMIT_LOGIN_CAPACITY,
        refill=settings.RATE_LIMIT_LOGIN_REFILL
    )
    await check_token_bucket(
        f"rl:login:email:{payload.email.lower()}",
        capacity=settings.RATE_LIMIT_LOGIN_CAPACITY,
        refill=settings.RATE_LIMIT_LOGIN_REFILL
    )

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
        "is_phone_verified": user.is_phone_verified,
    }

@router.post("/otp")
async def request_otp(request: Request, payload: OTPRequest):
    client_ip = get_client_ip(request)
    
    # 1. Multi-dimensional rate limit (IP + Phone)
    await check_token_bucket(
        f"rl:otp_send:ip:{client_ip}",
        capacity=settings.RATE_LIMIT_OTP_SEND_CAPACITY,
        refill=settings.RATE_LIMIT_OTP_SEND_REFILL
    )
    await check_token_bucket(
        f"rl:otp_send:phone:{payload.phone}",
        capacity=settings.RATE_LIMIT_OTP_SEND_CAPACITY,
        refill=settings.RATE_LIMIT_OTP_SEND_REFILL
    )

    # 2. CSPRNG generation of 6-digit OTP
    otp_code = "".join(secrets.choice("0123456789") for _ in range(6))


    print(f"OTP FOR NUMBER {payload.phone} IS {otp_code}")
    # 3. Cryptographic salt + SHA-256 hash storage (No plaintext in Redis)
    salt = secrets.token_hex(16)
    otp_hash = hashlib.sha256(f"{salt}:{otp_code}".encode("utf-8")).hexdigest()

    data = {
        "hash": otp_hash,
        "salt": salt,
        "attempts": 0,
        "created_at": time.time(),
    }

    # Store with expiration, invalidating any previous OTP for this phone
    await redis_client.setex(
        f"otp:{payload.phone}",
        settings.OTP_EXPIRE_SECONDS,
        json.dumps(data)
    )

    # In development mode only, log simulation notice without exposing to API
    if settings.ENV != "production":
        logger.info("[DEV ONLY SMS SIMULATION] Phone: %s | OTP: %s", payload.phone, otp_code)

    return {"message": "OTP sent"}

@router.post("/verify")
async def verify_otp(request: Request, payload: OTPVerify, db: AsyncSession = Depends(get_db)):
    client_ip = get_client_ip(request)
    
    # 1. Rate limit verification attempts (IP + Phone)
    await check_token_bucket(
        f"rl:otp_verify:ip:{client_ip}",
        capacity=settings.RATE_LIMIT_OTP_VERIFY_CAPACITY,
        refill=settings.RATE_LIMIT_OTP_VERIFY_REFILL
    )
    await check_token_bucket(
        f"rl:otp_verify:phone:{payload.phone}",
        capacity=settings.RATE_LIMIT_OTP_VERIFY_CAPACITY,
        refill=settings.RATE_LIMIT_OTP_VERIFY_REFILL
    )

    # 2. Retrieve cached record
    raw = await redis_client.get(f"otp:{payload.phone}")
    if not raw:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    try:
        data = json.loads(raw)
    except Exception:
        await redis_client.delete(f"otp:{payload.phone}")
        raise HTTPException(status_code=400, detail="Invalid OTP record")

    # 3. Check attempt limit
    attempts = data.get("attempts", 0)
    max_attempts = settings.OTP_MAX_ATTEMPTS
    if attempts >= max_attempts:
        await redis_client.delete(f"otp:{payload.phone}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum verification attempts exceeded. Please request a new OTP."
        )

    # 4. Constant-time hash comparison
    expected_hash = hashlib.sha256(f"{data['salt']}:{payload.code}".encode("utf-8")).hexdigest()
    if not hmac.compare_digest(expected_hash, data["hash"]):
        data["attempts"] = attempts + 1
        ttl = await redis_client.ttl(f"otp:{payload.phone}")
        if data["attempts"] >= max_attempts or ttl <= 0:
            await redis_client.delete(f"otp:{payload.phone}")
            raise HTTPException(
                status_code=400,
                detail="Invalid OTP. Maximum attempts exceeded. Please request a new OTP."
            )
        # Update attempt count with remaining TTL
        await redis_client.setex(f"otp:{payload.phone}", ttl, json.dumps(data))
        remaining = max_attempts - data["attempts"]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OTP code. {remaining} attempt(s) remaining."
        )

    # 5. Correct code: Invalidate immediately to prevent reuse (One-Time Use)
    await redis_client.delete(f"otp:{payload.phone}")

    # 6. Check if caller has an existing authenticated session
    auth_header = request.headers.get("authorization")
    current_auth_user = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            token_payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = token_payload.get("sub")
            if user_id:
                res = await db.execute(select(User).where(User.id == user_id))
                current_auth_user = res.scalar_one_or_none()
        except JWTError:
            pass

    now = datetime.now(timezone.utc)
    if current_auth_user:
        # Link verified phone to the authenticated user
        current_auth_user.phone = payload.phone
        current_auth_user.is_phone_verified = True
        current_auth_user.phone_verified_at = now
        await db.commit()
        await db.refresh(current_auth_user)
        access_token = create_access_token(data={"sub": str(current_auth_user.id), "role": current_auth_user.role})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": str(current_auth_user.id),
            "phone_verified": True,
            "message": "Phone successfully verified and linked."
        }

    # 7. Unauthenticated flow: Find or create user by phone
    result = await db.execute(select(User).where(User.phone == payload.phone))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            phone=payload.phone,
            email=f"{payload.phone}@otp.local",
            password_hash="",
            role="user",
            is_phone_verified=True,
            phone_verified_at=now,
        )
        db.add(user)
    else:
        user.is_phone_verified = True
        user.phone_verified_at = now

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "phone_verified": True,
    }