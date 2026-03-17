from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BFM AI Agent"
    app_env: str = "development"
    default_provider: str = "mock"
    sqlite_path: str = "data/bfm_demo.db"
    workbook_path: str = "data/bfm_demo_data.xlsx"
    upload_dir: str = "data/uploads"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1"
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2025-01-01-preview"
    azure_openai_deployment: str = "gpt-4.1"
    azure_openai_model: str = "gpt-4.1"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = Field(default="https://cloud.langfuse.com")
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None
    gmail_user_email: str | None = None

    @property
    def sqlite_file(self) -> Path:
        return ROOT_DIR / self.sqlite_path

    @property
    def workbook_file(self) -> Path:
        return ROOT_DIR / self.workbook_path

    @property
    def upload_path(self) -> Path:
        return ROOT_DIR / self.upload_dir

    @property
    def templates_dir(self) -> Path:
        return ROOT_DIR / "src" / "bfm_agent" / "templates"

    @property
    def static_dir(self) -> Path:
        return ROOT_DIR / "src" / "bfm_agent" / "static"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_file.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.workbook_file.parent.mkdir(parents=True, exist_ok=True)
    return settings
