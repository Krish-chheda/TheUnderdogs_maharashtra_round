import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    # App
    ENV: str = os.getenv("ENV", "development")
    
    # Database & Redis
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fairdrop")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Security & JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-key-for-24h-sprint")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))
    
    # Rate Limits (capacity, refill tokens per second)
    RATE_LIMIT_JOIN_IP_CAPACITY: int = int(os.getenv("RATE_LIMIT_JOIN_IP_CAPACITY", "20"))
    RATE_LIMIT_JOIN_IP_REFILL: float = float(os.getenv("RATE_LIMIT_JOIN_IP_REFILL", "2.0"))
    
    RATE_LIMIT_JOIN_USER_CAPACITY: int = int(os.getenv("RATE_LIMIT_JOIN_USER_CAPACITY", "5"))
    RATE_LIMIT_JOIN_USER_REFILL: float = float(os.getenv("RATE_LIMIT_JOIN_USER_REFILL", "0.5"))
    
    RATE_LIMIT_JOIN_EVENT_USER_CAPACITY: int = int(os.getenv("RATE_LIMIT_JOIN_EVENT_USER_CAPACITY", "3"))
    RATE_LIMIT_JOIN_EVENT_USER_REFILL: float = float(os.getenv("RATE_LIMIT_JOIN_EVENT_USER_REFILL", "0.2"))

    RATE_LIMIT_JOIN_EVENT_IP_CAPACITY: int = int(os.getenv("RATE_LIMIT_JOIN_EVENT_IP_CAPACITY", "30"))
    RATE_LIMIT_JOIN_EVENT_IP_REFILL: float = float(os.getenv("RATE_LIMIT_JOIN_EVENT_IP_REFILL", "3.0"))

    RATE_LIMIT_OTP_SEND_CAPACITY: int = int(os.getenv("RATE_LIMIT_OTP_SEND_CAPACITY", "3"))
    RATE_LIMIT_OTP_SEND_REFILL: float = float(os.getenv("RATE_LIMIT_OTP_SEND_REFILL", "0.05")) # 1 per 20s

    RATE_LIMIT_OTP_VERIFY_CAPACITY: int = int(os.getenv("RATE_LIMIT_OTP_VERIFY_CAPACITY", "5"))
    RATE_LIMIT_OTP_VERIFY_REFILL: float = float(os.getenv("RATE_LIMIT_OTP_VERIFY_REFILL", "0.1"))

    RATE_LIMIT_LOGIN_CAPACITY: int = int(os.getenv("RATE_LIMIT_LOGIN_CAPACITY", "10"))
    RATE_LIMIT_LOGIN_REFILL: float = float(os.getenv("RATE_LIMIT_LOGIN_REFILL", "0.5"))

    RATE_LIMIT_CLAIM_CAPACITY: int = int(os.getenv("RATE_LIMIT_CLAIM_CAPACITY", "5"))
    RATE_LIMIT_CLAIM_REFILL: float = float(os.getenv("RATE_LIMIT_CLAIM_REFILL", "0.5"))

    # OTP Security
    OTP_EXPIRE_SECONDS: int = int(os.getenv("OTP_EXPIRE_SECONDS", "300"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    
    # Fraud / Anti-Bot Farm
    IP_ACCOUNT_THRESHOLD: int = int(os.getenv("IP_ACCOUNT_THRESHOLD", "5"))
    IP_ACCOUNT_WINDOW_SECONDS: int = int(os.getenv("IP_ACCOUNT_WINDOW_SECONDS", "3600"))

    def validate_production_security(self):
        if self.ENV == "production":
            if self.JWT_SECRET in ("super-secret-key-for-24h-sprint", "", "secret") or len(self.JWT_SECRET) < 32:
                raise ValueError("FATAL: JWT_SECRET must be configured with at least 32 characters in production.")

settings = Settings()
settings.validate_production_security()
