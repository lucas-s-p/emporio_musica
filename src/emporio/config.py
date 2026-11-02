"""Application settings, loaded from environment variables and an optional .env file."""

from datetime import date
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_fallback_models: str = ""
    store_today: date | None = None
    data_dir: Path = Path("data")

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.openrouter_fallback_models.split(",") if m.strip()]