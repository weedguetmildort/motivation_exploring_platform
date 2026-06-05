import os
from functools import lru_cache

class Settings:
    # Mongo
    MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "mep_dev")

    # JWT / Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
    JWT_EXPIRES_MIN: int = int(os.getenv("JWT_EXPIRES_MIN", "180"))  # 3 hours

    COOKIE_NAME: str = os.getenv("COOKIE_NAME", "session")
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "").lower() in {"1","true","yes"}  # True in prod
    COOKIE_DOMAIN: str | None = os.getenv("COOKIE_DOMAIN") or None  # optional
    SAMESITE: str = os.getenv("COOKIE_SAMESITE", "Lax")  # "None" for cross-site in prod if needed

    # CORS / Frontend
    ALLOW_ORIGINS: list[str] = list(filter(None, [
        "http://localhost:3000",
        os.getenv("FRONTEND_ORIGIN"),  # e.g., https://<frontend>.herokuapp.com
    ]))

    # Environment
    ENV: str = os.getenv("ENV", "development")

    # Link Health & Discovery
    LINK_CHECK_INTERVAL_HOURS: int = int(os.getenv("LINK_CHECK_INTERVAL_HOURS", "12"))
    MAX_LIVE_LINKS_PER_SUBJECT: int = int(os.getenv("MAX_LIVE_LINKS_PER_SUBJECT", "30"))
    MAX_RETRIES_LINK_CHECK: int = int(os.getenv("MAX_RETRIES_LINK_CHECK", "3"))
    CANDIDATES_PER_CYCLE: int = int(os.getenv("CANDIDATES_PER_CYCLE", "1"))
    LINK_REQUEST_TIMEOUT: int = int(os.getenv("LINK_REQUEST_TIMEOUT", "10"))

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
