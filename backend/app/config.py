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
    env: str = "local"
    seed_demo: bool = False
    # Railway: volume on the storykeep service at /app/var, env DATA_DIR=/app/var.
    data_dir: Path = Path(__file__).resolve().parents[1] / "var"
    frontend_dir: Path | None = None
    s3_bucket: str | None = None
    s3_prefix: str = "storykeep"
    aws_region: str = "us-east-1"
    backup_interval_hours: int = 24
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket: str | None = None
    b2_endpoint: str = ""
    b2_region: str = ""
    refresh_minutes: int = 15
    extract_on_import: bool = True
    secure_cookies: bool = False
    xai_api_key: str = ""
    xai_chat_url: str = "https://api.x.ai/v1/chat/completions"
    xai_chat_model: str = "grok-4.6"
    xai_chat_models: str = "grok-4.6,grok-4.3"
    xai_chat_fast_model: str = "grok-4.3"
    xai_chat_max_tokens: int = 125_000
    chat_requests_per_hour: int = 120
    junior_cron_secret: str = ""
    xai_image_url: str = "https://api.x.ai/v1/images/generations"
    xai_image_edit_url: str = "https://api.x.ai/v1/images/edits"
    xai_imagine_model: str = "grok-imagine-image-2.0"
    imagine_requests_per_hour: int = 10
    stt_sessions_per_hour: int = 60
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    login_2fa_challenge_minutes: int = 10
    login_email_otp_max_attempts: int = 5
    fastmail_caldav_url: str = ""
    fastmail_token: str = ""
    fastmail_jmap_session_url: str = "https://api.fastmail.com/jmap/session"
    railway_api_token: str = ""
    railway_token: str = ""
    railway_project_id: str = ""
    railway_project_name: str = "Storykeep"
    railway_service_id: str = ""
    railway_service_name: str = "storykeep"
    railway_environment_id: str = ""
    railway_environment_name: str = "production"
    railway_public_domain: str = ""
    github_token: str = ""
    github_repo: str = "sb11b/Storykeep-"
    cursor_api_key: str = ""
    cursor_agent_repo: str = ""
    cursor_agent_branch: str = "main"
    cursor_api_url: str = "https://api.cursor.com"

    @property
    def cursor_configured(self) -> bool:
        return bool((self.cursor_api_key or "").strip())

    @field_validator("env", mode="before")
    @classmethod
    def normalize_env(cls, value: object) -> str:
        raw = str(value or "").strip().lower()
        railway = (os.getenv("RAILWAY_ENVIRONMENT") or "").strip().lower()
        if railway and (not raw or raw == "local"):
            return railway
        return raw or "local"

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
        return self.secure_cookies or self.env == "production"

    @property
    def object_bucket(self) -> str | None:
        bucket = (self.b2_bucket or self.s3_bucket or "").strip()
        return bucket or None

    @property
    def object_region(self) -> str:
        return (self.b2_region or self.aws_region or "us-east-1").strip()

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

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from.strip())

    @property
    def fastmail_calendar_configured(self) -> bool:
        """Per-user tokens. Missing FASTMAIL_* env still offers Connect (public CalDAV host)."""
        return True

    @property
    def railway_configured(self) -> bool:
        return bool((self.railway_api_token or self.railway_token or "").strip())

    @property
    def github_configured(self) -> bool:
        return bool((self.github_token or "").strip())


settings = Settings()
