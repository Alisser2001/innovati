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
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    # Microsoft Graph
    GRAPH_TENANT_ID: str | None = os.getenv("GRAPH_TENANT_ID")
    GRAPH_CLIENT_ID: str | None = os.getenv("GRAPH_CLIENT_ID")
    GRAPH_CLIENT_SECRET: str | None = os.getenv("GRAPH_CLIENT_SECRET")
    GRAPH_USER_UPN: str | None = os.getenv("GRAPH_USER_UPN") 
    GRAPH_POLL_INTERVAL_SECONDS: int = int(os.getenv("GRAPH_POLL_INTERVAL_SECONDS", "60"))

    # Habilitar/deshabilitar el poller
    ENABLE_EMAIL_POLLER: bool = _as_bool(os.getenv("ENABLE_EMAIL_POLLER"), False)

    # Gemini
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_TIMEOUT: int = int(os.getenv("GEMINI_TIMEOUT", "15"))

settings = Settings()
