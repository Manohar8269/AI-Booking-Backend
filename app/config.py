from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    lab_mode: Literal["secure", "vulnerable"] = "secure"
    mongodb_url: str = ""
    mongodb_database: str = "ai_booking_calendar"
    jwt_secret: str = Field(
        default="development-only-change-this-secret",
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET"),
    )
    jwt_expire_minutes: int = 60
    frontend_origins: str = Field(
        default="http://localhost:5173,https://ai-booking-frontend-k40y.onrender.com",
        validation_alias=AliasChoices("FRONTEND_ORIGIN", "FRONTEND_ORIGINS"),
    )
    approval_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    default_timezone: str = "Asia/Kolkata"
    meeting_match_threshold: float = Field(default=0.78, ge=0.5, le=1.0)
    seed_name: str = "Lab User"
    seed_email: str = ""
    seed_password: str = ""
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("default_timezone")
    @classmethod
    def validate_default_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("DEFAULT_TIMEZONE must be a valid IANA timezone") from exc
        return value

    def validate_lab_mode(self) -> None:
        if self.lab_mode == "vulnerable" and self.app_env.lower() != "development":
            raise ValueError("LAB_MODE=vulnerable is only allowed when APP_ENV=development")
        if self.app_env.lower() not in {"development", "test"} and self.jwt_secret == "development-only-change-this-secret":
            raise ValueError("Set SECRET_KEY to a unique secret before using a non-development environment")

    @property
    def cors_origins(self) -> list[str]:
        origins = []
        for value in self.frontend_origins.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                parsed = urlsplit(value)
            except ValueError:
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
                continue
            origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if origin not in origins:
                origins.append(origin)

        # Keep the deployed frontend allowed even if Render has an older
        # FRONTEND_ORIGIN value configured alongside FRONTEND_ORIGINS.
        deployed_frontend = "https://ai-booking-frontend-k40y.onrender.com"
        if deployed_frontend not in origins:
            origins.append(deployed_frontend)
        return origins

    @property
    def llm_configured(self) -> bool:
        base = self.openai_base_url.strip()
        if not base or not self.openai_api_key.strip() or not self.openai_model.strip():
            return False
        try:
            parsed = urlsplit(base)
        except ValueError:
            return False
        return parsed.scheme == "https" and bool(parsed.hostname) or (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_lab_mode()
    return settings
