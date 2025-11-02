from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from .config import get_settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    if not isinstance(password, str):
        password = str(password)
    password = password.strip()
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    if not isinstance(password, str):
        password = str(password)
    password = password.strip()
    return pwd_context.verify(password, hashed)

def create_access_token(subject: str) -> str:
    """Create a short-lived JWT for the given subject (user id or email)."""
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.JWT_EXPIRES_MIN)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
