import os
from dotenv import load_dotenv

load_dotenv()

def _as_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}

class Settings:
    # App
    APP_NAME: str = os.getenv("APP_NAME", "innovati-technical-test")
    ENV: str = os.getenv("ENV", "dev")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PORT: int = int(os.getenv("PORT", "8000"))

    # DB 
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./library.db")

settings = Settings()
