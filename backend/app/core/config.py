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

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    gemini_api_key: str = ""
    openweather_api_key: str = ""
    google_places_api_key: str = ""
    amadeus_api_key: str = ""
    amadeus_api_secret: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — avoids re-parsing env vars on every request."""
    return Settings()
