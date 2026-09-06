from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "COD Call Center"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://callcenter:callcenter@db:5432/callcenter"
    cors_origins: str = "http://localhost:3000"
    session_cookie_name: str = "cc_session"
    session_hours: int = 12
    cookie_secure: bool = False
    timezone: str = "Africa/Casablanca"
    admin_username: str = "owner"
    admin_password: str = "ChangeMeNow!123"
    admin_display_name: str = "Owner"
    app_secret: str = "change-this-app-secret-in-production"
    public_api_base_url: str = "http://localhost:8000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def normalized_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @field_validator("session_hours")
    @classmethod
    def validate_session_hours(cls, value: int) -> int:
        if value < 1 or value > 168:
            raise ValueError("SESSION_HOURS must be between 1 and 168")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
