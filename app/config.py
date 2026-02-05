"""Application configuration using pydantic-settings."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Database (SQLite for local dev, PostgreSQL for production)
    database_url: str = "sqlite:///./storage/video_material.db"

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Storage
    storage_base_path: Path = Path("./storage")
    input_dir: Path = Path("./storage/input")
    output_dir: Path = Path("./storage/output")
    processing_dir: Path = Path("./storage/processing")

    # GPU / Whisper
    whisper_model: str = "large-v3"
    whisper_compute_type: str = "float16"
    whisper_language: str = "ja"

    # Processing
    scene_detect_threshold: float = 0.3
    phash_threshold: int = 5
    max_concurrent_jobs: int = 2

    # Authentication
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_use_secrets_token_urlsafe_32"
    require_auth: bool = True

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        for dir_path in [
            self.storage_base_path,
            self.input_dir,
            self.output_dir,
            self.processing_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
