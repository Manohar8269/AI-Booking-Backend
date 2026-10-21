from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    lab_mode: Literal["secure", "vulnerable"] = "secure"
    database_url: str = "sqlite:///./lab.db"
    jwt_secret: str = Field(
        default="development-only-change-this-secret",
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET"),
    )
    jwt_expire_minutes: int = 60
    frontend_origins: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("FRONTEND_ORIGIN", "FRONTEND_ORIGINS"),
    )
    approval_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    seed_name: str = "Lab User"
    seed_email: str = ""
    seed_password: str = ""
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_lab_mode(self) -> None:
        if self.lab_mode == "vulnerable" and self.app_env.lower() != "development":
            raise ValueError("LAB_MODE=vulnerable is only allowed when APP_ENV=development")
        if self.app_env.lower() not in {"development", "test"} and self.jwt_secret == "development-only-change-this-secret":
            raise ValueError("Set SECRET_KEY to a unique secret before using a non-development environment")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

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
