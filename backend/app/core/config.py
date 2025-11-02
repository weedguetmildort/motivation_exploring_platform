import os
from functools import lru_cache

class Settings:
    # Mongo
    MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "mep_dev")

    # JWT / Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
    JWT_EXPIRES_MIN: int = int(os.getenv("JWT_EXPIRES_MIN", "60"))  # 60 minutes

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

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
