from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://storykeep:storykeep@127.0.0.1:5432/storykeep"
    secret_key: str = "change-me-in-production-storykeep"
    access_token_minutes: int = 60 * 24 * 14
    cors_origins: str = "http://127.0.0.1:43123,http://localhost:43123"
    seed_demo: bool = True
    data_dir: Path = Path(__file__).resolve().parents[1] / "var"
    s3_bucket: str | None = None
    s3_prefix: str = "storykeep"
    aws_region: str = "us-east-1"
    refresh_minutes: int = 15
    extract_on_import: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

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


settings = Settings()
