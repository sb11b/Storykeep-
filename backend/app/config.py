from pathlib import Path
import hashlib
import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _as_sqlalchemy_url(url: str) -> str:
    normalized = url.replace("postgres://", "postgresql://", 1)
    if normalized.startswith("postgresql://") and "+psycopg2" not in normalized and "+asyncpg" not in normalized:
        normalized = normalized.replace("postgresql://", "postgresql+psycopg2://", 1)
    return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://storykeep:storykeep@127.0.0.1:5432/storykeep"
    secret_key: str = "change-me-in-production-storykeep"
    access_token_minutes: int = 60 * 24 * 14
    cors_origins: str = "http://127.0.0.1:43123,http://localhost:43123"
    seed_demo: bool = True
    data_dir: Path = Path(__file__).resolve().parents[1] / "var"
    frontend_dir: Path | None = None
    s3_bucket: str | None = None
    s3_prefix: str = "storykeep"
    aws_region: str = "us-east-1"
    refresh_minutes: int = 15
    extract_on_import: bool = True
    secure_cookies: bool = False
    xai_api_key: str = ""
    xai_chat_model: str = "grok-4"
    xai_chat_max_tokens: int = 2048
    chat_requests_per_hour: int = 120

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not value:
            return value
        return _as_sqlalchemy_url(str(value))

    @field_validator("frontend_dir", mode="before")
    @classmethod
    def empty_frontend_dir(cls, value: object) -> object:
        if value == "" or value is None:
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [part.strip() for part in self.cors_origins.split(",") if part.strip()]
        public = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if public:
            origins.append(f"https://{public}")
        custom = os.getenv("RAILWAY_STATIC_URL")
        if custom:
            origins.append(f"https://{custom}")
        return origins

    @property
    def cookie_secure(self) -> bool:
        return self.secure_cookies or bool(os.getenv("RAILWAY_ENVIRONMENT"))

    @property
    def signing_key(self) -> str:
        if self.secret_key and self.secret_key != "change-me-in-production-storykeep":
            return self.secret_key
        return hashlib.sha256(f"storykeep:{self.database_url}".encode()).hexdigest()

    @property
    def backup_dir(self) -> Path:
        path = self.data_dir / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def archive_dir(self) -> Path:
        path = self.data_dir / "archives"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def tts_dir(self) -> Path:
        path = self.data_dir / "tts"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
