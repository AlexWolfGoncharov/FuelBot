"""
Configuration settings for the Fuel Tracker Bot
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Optional

from config.db_url import normalize_database_url_for_async


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Telegram Bot
    bot_token: str
    allowed_user_ids: List[int] = []

    @field_validator('allowed_user_ids', mode='before')
    @classmethod
    def parse_allowed_user_ids(cls, v):
        """Parse comma-separated string of user IDs into a list"""
        if isinstance(v, str):
            # Split by comma and convert to integers
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        elif isinstance(v, int):
            # Single integer - convert to list
            return [v]
        return v

    # AI Services
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: Optional[str] = None

    # Google Sheets (file locally; on Railway use GOOGLE_SHEETS_CREDENTIALS_JSON)
    google_sheets_credentials_file: str = "credentials.json"
    google_sheets_credentials_json: Optional[str] = None
    google_sheet_id: str

    # Database (local: sqlite; Railway: set DATABASE_URL from Postgres plugin)
    database_url: str = "sqlite+aiosqlite:///./fuel_tracker.db"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            return normalize_database_url_for_async(v)
        return v

    # Logging
    log_level: str = "INFO"

    # Тимчасовий HTML-дашборд (aiohttp на PORT разом з ботом)
    enable_web_dashboard: bool = True
    dashboard_ttl_seconds: int = 86400  # макс. 24 год
    # Публічний URL сервісу без слешу в кінці, напр. https://fuelbot-production.up.railway.app
    public_base_url: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Create global settings instance
settings = Settings()
