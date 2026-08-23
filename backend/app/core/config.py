"""
Application configuration loaded from environment variables.
Uses pydantic-settings so every value is typed and validated at startup
instead of failing silently deep inside the app later.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/voyagerai"
    database_connect_timeout_seconds: int = 5
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl_seconds: int = 3600
    chroma_persist_dir: str = "./chroma_data"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    gemini_api_key: str = ""
    openweather_api_key: str = ""
    google_places_api_key: str = ""
    amadeus_api_key: str = ""
    amadeus_api_secret: str = ""
    sentry_dsn: str = ""
    log_level: str = "INFO"

    rate_limiting_enabled: bool = True
    rate_limit_auth_rpm: int = 10
    rate_limit_message_rpm: int = 20
    rate_limit_general_rpm: int = 120

    admin_emails: str = "admin@example.com,admin@voyager.ai"

    @property
    def admin_emails_list(self) -> list[str]:
        return [email.strip().lower() for email in self.admin_emails.split(",") if email.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — avoids re-parsing env vars on every request."""
    return Settings()
